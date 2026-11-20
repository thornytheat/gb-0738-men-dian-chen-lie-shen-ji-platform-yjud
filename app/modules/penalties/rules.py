from app.modules.intake.catalog import CODES


def candidates(plan, evidence, cents):
    required, products = plan['sku'], evidence['products']
    observed = products.get(required)
    others = sorted(products.keys() - {required})
    findings = []
    if observed is None:
        findings.append(('MISSING_SKU', {'expected_sku': required, 'completed_sources': evidence['completed_sources']}))
    if others:
        findings.append(('WRONG_SKU', {'skus': others, 'sources': [line for code in others for line in products[code]['sources']]}))
    if observed is not None:
        if observed['facings'] < plan['facings']:
            findings.append(('UNDER_FACINGS', {'expected': plan['facings'], 'actual': observed['facings'], 'sources': observed['sources']}))
        if observed['price_cents'] != plan['price_cents']:
            findings.append(('PRICE_MISMATCH', {'expected': plan['price_cents'], 'actual': observed['price_cents'],
                                                'sources': observed['sources']}))
    return sorted(({'code': code, 'cents': cents[code], 'proof': proof} for code, proof in findings),
                  key=lambda finding: (-finding['cents'], CODES.index(finding['code'])))
