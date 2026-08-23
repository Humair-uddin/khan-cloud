# Khan Virtual Display upstream provenance

KG-008K6 rebases the production driver core onto the MIT-licensed
VirtualDrivers/Virtual-Display-Driver implementation at commit
`d7244969b2aa8bb38e76d79505eda217996cefea`.

The previous Microsoft-sample-derived Khan driver remains preserved in Git
history at commit `e68311976d4a3331a56809443697f67a0cbdc181` as the known-good
rollback/reference implementation.

Khan product identity, INF/package identity, policy, runtime configuration
namespace, orchestration boundary, tests, and deployment are Khan-owned.

Windows Driver Framework public UMDF 2.15 headers are pinned from
Microsoft/Windows-Driver-Frameworks at commit
`3b9780e847cf68d6199dafe0f87650cf1f9c227f`.
