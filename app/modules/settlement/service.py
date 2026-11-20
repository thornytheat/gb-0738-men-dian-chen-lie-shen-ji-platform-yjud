from time import perf_counter

from app.manifest import manifest
from app.pipeline import Audit


def run_audit(settings, store, options):
    start = perf_counter()
    audit = Audit(settings, options)
    run = manifest(audit)
    existing = store.get(run['run_id'], required=False)
    if existing is not None:
        return existing, True
    settlement = audit.settlement
    run['processing_ms'] = round((perf_counter() - start) * 1000, 3)
    snapshot = {'manifest': run, 'campaign': audit.intake['campaign'], 'intake': audit.intake, 'plans': audit.plans,
                'photos': audit.photos, 'coverage': audit.coverage, 'penalties': audit.penalties, 'settlement': settlement}
    return store.save(snapshot)
