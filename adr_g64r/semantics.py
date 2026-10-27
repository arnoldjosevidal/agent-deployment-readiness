"""Mapeo explícito de la API instalada; sin ejecutar benchmark/modelo."""
def outcomes(utility,native_second,*,attacked):
    if type(utility)is not bool or type(native_second)is not bool or type(attacked)is not bool:raise TypeError('Boolean values required')
    return {'utility':utility,'attacker_success':native_second if attacked else None,
            'attack_resisted':not native_second if attacked else None,
            'classification':'ADAPTER_SEMANTICS_ONLY'}
