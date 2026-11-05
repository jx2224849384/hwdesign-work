# Wire layout

**Obtain every row below by serializing an instance with Waveflow and writing
down what came out.** Do not derive it by reading the schema. Hand-derived
layouts are where packing bugs come from, and this file exists to make the
real one visible before any C++ is written.

For each of the command header, the response header, the footer and the
sample burst: the word index, the bit range, the field, and its type.

## Command header

| Word | Bits | Field | Type |
| --- | --- | --- | --- |
| | | | *TODO* |

## Response header

| Word | Bits | Field | Type |
| --- | --- | --- | --- |
| | | | *TODO* |

## Response footer

| Word | Bits | Field | Type |
| --- | --- | --- | --- |
| | | | *TODO* |

## Sample burst

Samples per word, packing order, and what happens to an odd final sample.

*TODO*
