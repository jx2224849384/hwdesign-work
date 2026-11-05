# Serialized wire layout

Observed through Waveflow schema/array serialization, recorded in `evidence/layout.json`.

| Structure | Observed words (hex) | TLAST positions (1-based) |
|---|---|---|
| CONFIG: tx=0xf1234567, R=2, C=3 | 00000001 f1234567 00000002 00000003 | 4 |
| Samples: -32768, -1, 0, 32767 | ffff8000 ffffffff 00000000 00007fff | 4 |
| DATA response: tx=0xffffffff, R=1 | 00000002 ffffffff 00000001 | 3 |
| Result: sixteen copies of 32767 times -32768 | 00080000 fffffffc | 2 |

Command words are opcode, tx_id, arg0, arg1, each occupying all 32 bits. Response header words are opcode, tx_id, rows. Payload samples occupy one sign-extended 32-bit word each. Results occupy two words each, low then high; only the final high word terminates the result burst. No footer or empty payload burst exists. TKEEP and TSTRB are 0xf.

Decisions: configuration is a staged CONFIG payload; only successful DATA gets a response; zero dimensions/data lengths are invalid; validation order is framing/opcode/configuration/arguments/payload; schema serialization determines packing; no rounding or saturation; IDs are arbitrary uint32 and errors record the received ID or zero before its arrival; every header and payload TLAST is checked; unused opcodes fail with code 2; no footer. See `assumptions.md` for integration choices.
