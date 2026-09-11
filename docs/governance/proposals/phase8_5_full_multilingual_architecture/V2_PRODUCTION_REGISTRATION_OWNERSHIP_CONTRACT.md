# V2 Production Registration Ownership Contract

Status: GOVERNED — IMPLEMENTATION BOUNDARY FROZEN  
Version: 1  
Scope: internal Full Multilingual V2 production composition only.

## Repository dependency evidence

`mnemo-core` defines application models, protocols, retrieval services, and `FullMultilingualV2EvaluationRuntimeFactory`. It does not depend on `mnemo-server`. `mnemo-server` depends on `mnemo-core`, derives `PrincipalContextV1` from validated server claims, and owns `CentralAuthorizationServiceV1`.

Importing the server package into core would reverse the existing dependency direction. Moving or duplicating central authorization would create a second security authority. Neither is permitted.

## Ownership decision

Core owns typed ports and authorization-independent application composition. Server owns production registration of the security-sensitive implementations. The additive server port is `FullMultilingualV2ServerDependencyAssemblerV1`; the server registration root is `ServerOwnedFullMultilingualV2RegistrationV1`.

The registration root creates `CentralAuthorizationServiceV1` from the server-owned `KnowledgeEngine`, supplies it to the future dependency assembler, and then passes the fully assembled core dependencies to the existing core factory. It does not register an MCP, HTTP, SSE, or stdio route and does not alter capability exposure.

## Deferred implementation

This contract does not implement the five production adapters. The dependency assembler intentionally has no production implementation in this remediation. A later authorized phase must implement it server-side using the governed V2 ports and existing storage infrastructure.

## Evaluator boundary

An evaluator may receive only `ComposedFullMultilingualV2Runtime`. It cannot receive the server authorization service, engine/storage handle, assembler, provider, generation selector, evidence store, resolver, or candidate projector.

## Compatibility

V1 routes, services, authorization, aliases, and storage contracts are unchanged. The registration boundary is internal and V2-only.
