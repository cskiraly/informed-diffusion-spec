import NoStallEquivModel
/-! For the twinstep check: the generated definitions the proofs take, as Lean prints them. Run by `check.sh`. -/
set_option pp.proofs false
#print NoStallEquiv.promiseDue.ext.tr
#print NoStallEquiv.parkOther.ext.tr
#print NoStallEquiv.stutter.ext.tr
#print NoStallEquiv.retryNoop.ext.tr
#print NoStallEquiv.retryAsk.ext.tr
#print NoStallEquiv.lrAsk.ext.tr
#print NoStallEquiv.NextTr
