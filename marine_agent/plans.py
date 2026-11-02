"""Bounded plan registry with optional SQLite persistence and atomic revisions."""
from collections import OrderedDict
import copy
import threading
import time
import os
import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from uuid import uuid4

from . import enrichment, planner
from .browser_transit import budgeted


class PlanError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


class PlanStore:
    def __init__(self, capacity=128, ttl=7200, persistent=False):
        self.capacity, self.ttl = capacity, ttl
        self.entries = OrderedDict()
        self.lock = threading.RLock()
        self.persistent = persistent

    @contextmanager
    def database(self):
        from .config import DATA
        path=Path(os.environ.get('PLANS_DB_PATH',str(DATA/'plans.sqlite3')))
        path.parent.mkdir(parents=True,exist_ok=True)
        c=sqlite3.connect(path,timeout=10)
        c.execute('PRAGMA journal_mode=WAL')
        c.execute('CREATE TABLE IF NOT EXISTS plans(id TEXT PRIMARY KEY,revision INTEGER,expires REAL,body TEXT,previous TEXT)')
        try:
            with c:yield c
        finally:c.close()

    def load(self,plan_id):
        if not self.persistent:return
        with self.database() as c:
            c.execute('DELETE FROM plans WHERE expires<=?',(time.time(),))
            row=c.execute('SELECT expires,body,previous FROM plans WHERE id=?',(plan_id,)).fetchone()
        if row:
            self.entries[plan_id]=dict(plan=json.loads(row[1]),previous=json.loads(row[2]) if row[2] else None,
                expires=time.monotonic()+max(0,row[0]-time.time()))
        else:self.entries.pop(plan_id,None)

    def save(self,result,previous=None,expected=None):
        if not self.persistent:return
        with self.database() as c:
            c.execute('BEGIN IMMEDIATE')
            c.execute('DELETE FROM plans WHERE expires<=?',(time.time(),))
            if expected is None:
                c.execute('INSERT INTO plans VALUES(?,?,?,?,?)',(result['plan_id'],result['revision'],time.time()+self.ttl,json.dumps(result,ensure_ascii=False),None))
                c.execute('DELETE FROM plans WHERE id IN (SELECT id FROM plans ORDER BY expires DESC LIMIT -1 OFFSET ?)',(self.capacity,))
            else:
                changed=c.execute('UPDATE plans SET revision=?,body=?,previous=? WHERE id=? AND revision=?',
                    (result['revision'],json.dumps(result,ensure_ascii=False),json.dumps(previous,ensure_ascii=False) if previous else None,result['plan_id'],expected)).rowcount
                if not changed:raise PlanError(409,'이미 변경되거나 만료된 일정입니다. 최신 일정을 확인하세요.')

    def latest(self,plan_id):
        with self.lock:
            self.prune();self.load(plan_id)
            entry=self.entries.get(plan_id)
            if not entry:raise PlanError(410,'일정 보관 시간이 지났습니다. 새로 생성해 주세요.')
            return copy.deepcopy(entry['plan'])

    def prune(self):
        now = time.monotonic()
        for key in [k for k, v in self.entries.items() if v['expires'] <= now]:
            del self.entries[key]

    def get(self, plan_id, revision):
        with self.lock:
            self.prune()
            self.load(plan_id)
            entry = self.entries.get(plan_id)
            if not entry:
                raise PlanError(410, '일정 보관 시간이 지났거나 서버가 재시작되었습니다. 일정을 다시 생성해 주세요.')
            if entry['plan']['revision'] != revision:
                raise PlanError(409, '이미 변경된 일정입니다. 최신 일정으로 다시 시도해 주세요.')
            return copy.deepcopy(entry['plan'])

    @budgeted
    def register(self, plan, plan_id=None):
        # A stable graph-attempt ID makes replay after registration idempotent.
        if plan_id:
            try:return self.latest(plan_id)
            except PlanError as error:
                if error.status!=410:raise
        result = copy.deepcopy(plan)
        result.update(plan_id=plan_id or uuid4().hex, revision=1, can_undo=False)
        for day in result['days']:
            for item in day['items']:
                item['slot_id'] = uuid4().hex
        enrichment.enrich(result)
        with self.lock:
            self.save(result)
            self.prune()
            while len(self.entries) >= self.capacity:
                self.entries.popitem(last=False)
            self.entries[result['plan_id']] = dict(plan=result, expires=time.monotonic() + self.ttl, previous=None)
        return copy.deepcopy(result)

    def commit(self, result, revision, previous):
        with self.lock:
            self.get(result['plan_id'], revision)
            result['revision'] = revision + 1
            result['can_undo'] = previous is not None
            self.save(result,previous,revision)
            self.entries[result['plan_id']].update(plan=copy.deepcopy(result), previous=previous)
            return copy.deepcopy(result)

    def set_lock(self, plan_id, revision, slot_id, locked):
        result = self.get(plan_id, revision)
        day = next((d for d in result['days'] if any(i['slot_id'] == slot_id for i in d['items'])), None)
        if day is None:
            raise PlanError(404, '방문을 찾을 수 없습니다.')
        item = next(i for i in day['items'] if i['slot_id'] == slot_id)
        original = item.get('original_kind') or item['kind']
        if original not in ('tourism', 'marine'):
            raise PlanError(422, '이 일정은 화면에서 고정·해제할 수 없습니다.')
        locks = result['trip']['locked']
        matching = lambda l: l['date'] == day['date'] and l['start'] == item['start'] and l['end'] == item['end'] and l['title'] == item['title']
        result['trip']['locked'] = [l for l in locks if not matching(l)]
        if locked:
            if len(result['trip']['locked']) >= 12:
                raise PlanError(422, '고정 일정은 최대 12개입니다.')
            result['trip']['locked'].append(dict(date=day['date'], start=item['start'], end=item['end'], title=item['title'],
                id=item.get('id'), lat=item.get('lat'), lon=item.get('lon'), original_kind=original))
        item['kind'] = 'locked' if locked else original
        item['original_kind'] = original
        return self.commit(result, revision, None)

    @budgeted
    def replace(self, plan_id, revision, slot_id, candidate_id):
        current = self.get(plan_id, revision)
        result = copy.deepcopy(current)
        target_day = next((d for d in result['days'] if any(i['slot_id'] == slot_id for i in d['items'])), None)
        if target_day is None:
            raise PlanError(404, '교체할 방문을 찾을 수 없습니다.')
        slot = next(i for i in target_day['items'] if i['slot_id'] == slot_id)
        locks = result['trip'].get('locked', [])
        if slot['kind'] != 'tourism' or any(l['date'] == target_day['date'] and l['start'] == slot['start'] and l['end'] == slot['end'] for l in locks):
            raise PlanError(409, '고정 일정·해양 체험은 교체할 수 없습니다. 고정을 먼저 해제해 주세요.')
        valid_ids = {p['id'] for p in target_day['alternatives']}
        if result['trip'].get('island_id'):
            from . import islands
            try:
                candidates = islands.candidates(islands.resolve(result['trip']['island_id']), result['trip']['excluded_ids'])
            except islands.IslandUnavailable as error:
                raise PlanError(422, str(error)) from None
        else:
            candidates = planner.tourism_candidates(result['trip']['region'], limit=200)
        candidate = next((p for p in candidates if p['id'] == candidate_id and p['id'] in valid_ids), None)
        used = {i.get('id') for d in result['days'] for i in d['items']}
        if candidate is None or candidate_id in used or candidate_id in result['trip']['excluded_ids']:
            raise PlanError(422, '현재 선택할 수 없는 대체 관광지입니다.')
        from . import rules
        trip = planner.Trip.model_validate(result['trip'])
        check = rules.assess(candidate,trip,target_day['date'],slot['start'],slot['end'],target_day.get('weather',{}),rules.reviewed_venues(),target_day.get('transport'))
        if not check['allowed']:
            raise PlanError(422, '날씨·운영·이용 조건에 맞지 않아 교체하지 않았습니다. '+ ' '.join(rules.MESSAGES[c] for c in check['codes']))
        if result['trip']['region'] not in planner.regions.LEGACY and not result['trip'].get('island_id'):
            from .mobility import route_between
            gateway=planner.regions.gateway(result['trip']['region'])
            if gateway is None or route_between(gateway,candidate,'car')['status'] != 'available':
                raise PlanError(422,'관광 탐색 기준점에서 도로 접근을 확인하지 못해 교체하지 않았습니다.')
        slot.update(candidate, reason='선택한 대체 관광지로 기존 시간대를 유지해 교체했어요.',
                    rule_evidence=check, checks=['운영시간·휴무', '동행 이용 조건'])
        if not rules.walk_fits(target_day['items'],trip,target_day.get('weather',{}),target_day.get('transport',trip.transport)):
            raise PlanError(422,'도보 이동량 기준을 초과하거나 거리를 확인하지 못해 교체하지 않았습니다.')
        new_route = enrichment.day_route(target_day)
        adjacent = [r for r in new_route['legs'] if slot_id in (r['from_slot'], r['to_slot'])]
        if any(r['status'] != 'available' for r in adjacent):
            raise PlanError(422, '인접 이동 경로를 확보하지 못해 교체하지 않았습니다.')
        if any(not r['fits_schedule'] for r in adjacent):
            raise PlanError(422, '이동시간이 기존 일정의 여유 시간보다 길어 교체하지 않았습니다.')
        if any(r['duration_s']>max(0,r['available_minutes']-rules.profile(trip)['route_buffer_minutes'])*60 for r in adjacent):
            raise PlanError(422,'동행 인원의 이동 준비·집결 여유를 확보하지 못해 교체하지 않았습니다.')
        planner.validate_schedule(result['days'])
        used = {i.get('id') for d in result['days'] for i in d['items']}
        for day in result['days']:
            day['alternatives'] = [p for p in candidates if p['id'] not in used and p['id'] not in result['trip']['excluded_ids']][:6]
        result['explanation_outdated'] = True
        enrichment.enrich(result)
        return self.commit(result, revision, current)

    def undo(self, plan_id, revision):
        with self.lock:
            self.get(plan_id, revision)
            previous = self.entries[plan_id]['previous']
            if previous is None:
                raise PlanError(409, '되돌릴 변경이 없습니다.')
            result = copy.deepcopy(previous)
            return self.commit(result, revision, None)


store = PlanStore(persistent=True)
