# Security Policy

## Supported versions

This project is pre-1.0; only the latest released version is supported.

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Use GitHub's private vulnerability reporting:
**Security → Report a vulnerability** on the repository, or open a private
advisory. We aim to acknowledge reports within a few days.

## Handling untrusted input

`controlm-chain-admin` parses XML using Python's standard-library
`xml.etree.ElementTree`. While ElementTree is not vulnerable to classic
billion-laughs entity expansion to the same degree as some parsers, you should
still treat **untrusted XML with caution**:

- Import exports from sources you trust.
- The tool does not resolve external DTDs or network entities, but very large or
  deeply nested documents can still consume significant memory (see the
  notes in DESIGN.md).
