# Local changes to arduino-lepton

Vendored from https://github.com/ducky64/arduino-lepton at commit
`eefa590f5a73bce3a086dd295524953b3cb1b1bc` (BSD-3-Clause, see LICENSE).

Changes:

1. `readVoSpi()`: removed the unused CRC read that indexed `header[4]` (out of bounds).
2. `readReg()`: a short I²C read now returns false (and drains the RX buffer) instead of true.
3. `readNonBusyStatus()`: gives up after `kBusyTimeoutMillis` (1 s) instead of looping forever.
4. `readVoSpi()`: if the first segment read carries ttt 2–4 (the read started mid-frame), the rest
   of that segment is clocked out and the frame is dropped without the 185 ms CS-high resync.
   Packet-number errors and later ttt mismatches still trigger a full resync.
5. `readVoSpi()`: the stack VLA scratch buffer became the member `dummyBuf_[240]`.
6. Added `VoSpiStats` counters (`resyncs`, `outOfPhase`, `discardSegments`) and `getVoSpiStats()`.
7. Added `setSpiClock()`; `readVoSpi()` uses it instead of the fixed 20 MHz `kDefaultSpiSettings`.
8. `readVoSpi()`: a ttt=0 (non-unique) segment at the start of a frame is drained and the call
   returns false, instead of spinning inside the call until the next valid segment 1. With VSYNC
   the capture task then sleeps between segments.
9. Added `packets`, `discardPackets` and `lastHeader` to `VoSpiStats` for wiring diagnostics.
10. Added `setStartWait()`: when no frame is in progress, `readVoSpi()` keeps reading discard packets for up to that long before returning (default 0 = original behaviour).
