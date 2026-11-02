import {mergeStep} from './execution-graph.js?v=0.9.0';
export const isActiveRun = run => ['queued', 'running'].includes(run?.status);
const isJourney = run => ['ai_plan', 'rules_plan'].includes(run.kind);
const newest = (a, b) => String(b.started_at || '').localeCompare(String(a.started_at || ''));

export function mergeRun(previous, incoming) {
  if (previous && !isActiveRun(previous) && isActiveRun(incoming)) return previous;
  const steps = new Map((previous?.steps || []).map(s => [s.id, s]));
  for (const step of incoming.steps || []) steps.set(step.id, mergeStep(steps.get(step.id), step));
  return { ...previous, ...incoming, steps: [...steps.values()] };
}
export function trimRuns(cache, selected, capacity = 40) {
  const rows = [...cache.values()].sort((a, b) =>
    Number(b.id === selected) - Number(a.id === selected) ||
    Number(isActiveRun(b)) - Number(isActiveRun(a)) || newest(a, b));
  const keep = new Set(rows.slice(0, capacity).map(r => r.id));
  for (const id of cache.keys()) if (!keep.has(id)) cache.delete(id);
}
export function chooseRun(cache, selected, follow) {
  if (!follow && cache.has(selected)) return selected;
  const rows = [...cache.values()].sort(newest);
  return rows.find(r => isJourney(r) && isActiveRun(r))?.id ||
    rows.find(isJourney)?.id || rows.find(isActiveRun)?.id || rows[0]?.id || null;
}
export function restoreRuns(cache, snapshot, selected, follow) {
  const previous = new Map(cache); cache.clear();
  for (const row of snapshot.filter(Boolean)) cache.set(row.id, mergeRun(previous.get(row.id), row));
  if (!follow && previous.has(selected) && !cache.has(selected)) cache.set(selected, previous.get(selected));
  const next = chooseRun(cache, selected, follow); trimRuns(cache, next); return next;
}
export function updateRun(cache, incoming, selected) {
  cache.set(incoming.id, mergeRun(cache.get(incoming.id), incoming)); trimRuns(cache, selected);
}
export function updateStep(cache, runId, step, selected) {
  const run = cache.get(runId) || {id: runId, kind: 'plan', status: 'running', started_at: step.started_at, steps: []};
  const next = mergeRun(run, {id: runId, steps: [step]}); cache.set(runId, next); trimRuns(cache, selected);
}
