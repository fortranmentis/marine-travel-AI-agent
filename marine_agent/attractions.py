"""Explicit exclusions for generic facilities in automatic tourism suggestions."""
import re

# TourAPI categoryCode2 A02/A0206 names verified from the source on 2026-10-16.
EXCLUDED_CATEGORIES = {
    'A02060400':'컨벤션센터', 'A02060600':'공연장', 'A02060700':'문화원',
    'A02060800':'외국문화원', 'A02060900':'도서관', 'A02061000':'대형서점',
    'A02061200':'영화관', 'A02061300':'어학당', 'A02061400':'학교',
}
GENERIC = re.compile(r'문화(?:예술)?회관|주민(?:자치)?센터|행정복지센터|구민회관|시민회관|복지관|'
                     r'종합운동장|공설운동장|체육관|체육센터|스포츠센터|축구장|테니스장|볼링장|헬스장|골프장|컨트리클럽')


def exclusion_reason(row):
    if str(row.get('cat3')) in EXCLUDED_CATEGORIES:
        return '관람·체험 프로그램 미확인 시설: '+EXCLUDED_CATEGORIES[str(row['cat3'])]
    if GENERIC.search(str(row.get('title') or '')):
        return '일반 공공·생활·체육시설'
    return None


def eligible(row):
    return str(row.get('contenttypeid')) in ('12','14','28') and exclusion_reason(row) is None
