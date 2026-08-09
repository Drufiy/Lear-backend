"""Track B — read connectors. Owner: Aradhya. See PRASH_V2.md §6.

A connector's job is narrow and consistent across every provider:
authenticate -> locate the resource -> fetch logs/status -> poll state.
Modeled on prash-backend's vercel_client.py, which already proves the
pattern out.

Every connector that has a meaningful notion of "the previous good
state" (Cloud Run, Vercel, k8s Deployments) should expose a
get_previous_revision()-shaped read call. Track C's rollback action
calls that directly -- there is deliberately no separate release-
history store. See PRASH_V2.md §6, cross-track dependency #2.
"""
