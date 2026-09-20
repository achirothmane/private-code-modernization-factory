# Wave 7G — Provider-Neutral Model Runner + Scorer

Date: 2026-09-20

## Goal

Build the measurement layer required to benchmark the first real semantic survivor without coupling ModFactory to one model provider and without inventing provider metrics.

## Components

### Request contract

`modfactory model-request` freezes:

- task ID and deterministic benchmark ID;
- provider/model identity;
- exact context bundle;
- exact allowed-change paths;
- full-file SHA-256 hashes;
- model instructions;
- response schema.

It does not call a provider.

### Provider-neutral runner

A provider adapter implements `invoke(request)`.

The core runner:

- validates request integrity;
- checks provider/model identity;
- measures wall-clock latency itself;
- records provider-returned input/output tokens when available;
- records provider-returned cost when available;
- leaves unknown token/cost metrics null.

A fake adapter unit test validates this behavior. No network inference is performed by the test.

### Response scorer

`modfactory model-score`:

- validates response schema and identity;
- rejects a tampered request;
- rejects a repository whose context files changed after request generation;
- blocks path traversal;
- blocks binary patches;
- blocks file create/delete/rename/copy operations;
- blocks files outside the exact allowlist;
- checks and applies a unified diff only in a temporary repository copy;
- rescans before/after;
- requires target finding removal;
- requires legacy usage removal;
- requires no new findings;
- requires non-increasing risk and no new dependency cycles;
- optionally runs project test commands only with explicit opt-in.

The original repository is never modified.

## Real contract validation

Pinned semantic survivor:

- repository: auth0/node-wsfed
- commit: 3bd751a1749d8746b981ce0e8daabe9eaec654b0
- migration: request~2.88.2 in seven test-suite usage sites

Workflow run: 35487640138
Artifact: 10598316289

Generated request:

- benchmark ID: 126397b865a6199a
- task ID: model-d866304f07
- context files: 8
- usage-site files: 7
- allowed-change paths: 8
- context characters: 38,731
- context band: small
- provider invoked: false
- project code executed: false

## Current compute decision

Ordinary-model benchmark infrastructure: **ready**

Ordinary-model quality benchmark actually executed: **no**

Long-context model benchmark: **not justified**

B300 benchmark/rental: **not justified**

The next valid evidence-producing step is one measured ordinary-model run on benchmark `126397b865a6199a` through a provider adapter that exposes stable model identity and provider usage/cost metadata.
