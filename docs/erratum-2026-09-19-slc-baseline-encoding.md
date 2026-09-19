# SLC/SLCQ baseline hash erratum before native execution

Recorded on 2026-09-19 during the first SLCQ intercepted test run, before any
SLCQ native request. The [SLC result](results-2026-09-19-public-source-search-baseline.md)
and [initial SLCQ protocol](prereg-2026-09-19-public-source-locator-qwen-comparison.md)
reported hash `8e8405087757368672736a43d858094349bea6c295029ffe4ea8a3ef15c385d8`
but described Python sorted compact ASCII JSON without specifying integer-valued
float normalization. That description was incomplete. Preserve those dated
documents and this explicit correction rather than silently changing a hash.

## Reproduction and exact identities

The unchanged committed SLC observer returned available, the same six cases,
five acceptable positive keyword sets and the same no-fit empty set. Encoding
that Python result with `json.dumps(value, sort_keys=True, separators=(',', ':'),
ensure_ascii=True, allow_nan=False).encode('ascii')`, with no trailing newline,
produces **4,458 bytes**, SHA-256:

`ef2ba8075ebbcb7eac467071cd673ecd4ac6cca3b111e20d945d7feb9e7d66ce`.

Recursively replacing integer-valued floats by integers before that encoding
produces **4,438 bytes**, SHA-256:

`8e8405087757368672736a43d858094349bea6c295029ffe4ea8a3ef15c385d8`.

The ten positive-reference coverage values (`0.0` and `1.0`) account for the
twenty-byte difference. IDs, hit sets, labels, questions, fixture bytes and
observed outcomes are unchanged. This reproduction establishes the omitted
normalization, not an attested reconstruction of the earlier hashing tool.

## Binding decision

For the NEW SLCQ runner only, this correction supersedes the original protocol's
baseline hash/encoding description: require the unmodified Python observation
and the **ef2ba807...** hash above. Keep **8e840508...** explicitly named as the
historically recorded, integer-normalized identity, not an alternative admission
hash. Do not normalize new results, accept either hash, loosen state checks,
modify the old observer/fixture or erase the failed first validation.

Bind both this erratum and the original protocol in the runner identity,
configuration and operator manifest. The historical SLC CLI/model lane remains
unchanged. This is not a new fixture, updated reference or retrospective result
pass. No Qwen budget, data scope, request limit, prompt or production boundary
changes; independent review, full regression and green CI remain required.

## Verification responsibility

The first draft produced 47 passing and 47 failing focused tests because valid
paths all stopped at this same baseline identity gate; that is one unsuccessful
validation of one problem, not 47 independent production defects. The gate
correctly refused to continue into the mocked paid path.

New tests must admit the actual unchanged Node observation, retain this exact
unmodified hash and reject normalized/tampered/unavailable observations before
key lookup or output creation. A real baseline-check mutation must make an
unchanged regression assertion fail. Later passing tests and native outcomes
are recorded separately; this erratum is not itself native execution evidence.
