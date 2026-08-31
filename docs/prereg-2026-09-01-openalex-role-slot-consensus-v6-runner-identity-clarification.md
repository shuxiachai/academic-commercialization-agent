# Pre-registration clarification: v6 derived request identities

**Frozen:** 2026-09-01, after commit `488276f` and before implementing a v6
runner or model adapter, constructing a provider client, or sending any Y or Z
request.

The development-runner pre-registration used the phrase "all 24 possible model
requests" when describing the pre-provider manifest. Exact Qwen prompts contain
OpenAlex titles and abstracts that do not exist locally until the corresponding
provider response arrives. Claiming those complete prompt hashes before
retrieval would therefore be an impossible and false durability boundary.

The executable interpretation is narrower and stronger at the real seam:

1. the global manifest commits all eight OpenAlex requests and all 24
   code-owned model request **templates** before constructing the OpenAlex
   adapter;
2. each complete OpenAlex response or failure journal is durable before a
   model call or later provider request;
3. after a successful provider response, the runner derives and writes that
   case's complete three-request model plan, including actual input and prompt
   hashes;
4. only after that plan is durable may the runner construct the Qwen adapter,
   if no earlier case required one, or send the first Qwen request; and
5. each Qwen journal is durable before another Qwen request, and the case audit
   is durable before the next OpenAlex request.

The pre-provider template identity binds method, case, pass order, profile and
fixed judge contract without pretending to know future candidate bytes. Each
derived request identity additionally binds candidate order, complete input,
complete prompt, exact model, endpoint, timeout and output-token ceiling. Tests
must observe both boundaries: the manifest before the OpenAlex adapter factory,
and the provider journal plus three-request case plan before the Qwen adapter
factory or outbound model call.

This clarification changes no method, query, role, prompt, threshold, request
ceiling, cost ceiling or cohort. It authorizes no network, model, label or
production access. It exists solely to prevent an implementation from either
claiming unknowable pre-retrieval prompt hashes or weakening the real
post-retrieval, pre-model write-once boundary.
