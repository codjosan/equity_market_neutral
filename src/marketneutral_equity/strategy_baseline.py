"""Naive and intentionally expensive sector-balanced short-term reversal."""

class SimpleReversalBaseline:
    def on_day(self, context):
        candidates={}
        for s, meta in context.universe.items():
            h=context.history[s]
            if len(h)<7 or h[-6]["close"] <= 0:
                continue
            ret=h[-1]["close"]/h[-6]["close"]-1.0
            candidates.setdefault(meta["sector"],[]).append((ret,s))
        target={s:0.0 for s in context.universe}
        for sector, vals in candidates.items():
            vals.sort()
            longs=[s for _,s in vals[:2]]
            shorts=[s for _,s in vals[-2:] if context.bars[s]["borrow_available"]]
            # Must keep balanced book when a short borrow locate is missing.
            size=min(len(longs),len(shorts))
            for s in longs[:size]:target[s]=0.025
            for s in shorts[:size]:target[s]=-0.025
        return target
