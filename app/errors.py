class AuditError(Exception):
    def __init__(self, code, message, status=422, evidence=None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.evidence = evidence

    def payload(self):
        detail = {'code': self.code, 'message': str(self)}
        if self.evidence is not None:
            detail['evidence'] = self.evidence
        return {'detail': detail}
