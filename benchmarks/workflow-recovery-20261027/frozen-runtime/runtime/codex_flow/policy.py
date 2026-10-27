from .contracts import RouteDecision

def route(*, independent_steps=1, conflicting_paths=False, risk_level='normal', single=False, mercury=None):
    if risk_level not in ('normal','low'): return RouteDecision('escalate','risk requires human scope decision')
    if single or independent_steps<2 or conflicting_paths:
        return RouteDecision('single','sequential task or conflicting ownership')
    if mercury and mercury.get('status')=='OBSERVED' and mercury.get('route')=='parallel':
        return RouteDecision('parallel','bounded typed recommendation','mercury',confidence=mercury.get('confidence'))
    if mercury and mercury.get('status')=='OBSERVED' and mercury.get('route')=='single':
        return RouteDecision('single','typed routing prefers single','mercury',confidence=mercury.get('confidence'))
    return RouteDecision('parallel','independent owned work available',fallback_reason=(mercury or {}).get('reason'))
