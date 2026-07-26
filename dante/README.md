# NTC Dante / AES67 Runtime Configuration

`NTC-Infrastructure` owns the reviewed production SDP and service templates.
`NTC-Runtime` remains the live bind-mounted state directory because the Dante
container mounts `/root/NTC-Runtime/dante` at `/app/data`.

Apply the managed SDP files with:

```sh
/root/NTC-Infrastructure/scripts/deploy-dante-aes67-runtime.sh
```

The deployment script copies the checked-in SDP files to
`/root/NTC-Runtime/dante/aes67` and installs the MixAssist AES67 systemd unit.
It does not restart the NTC-Dante webcall bridge.

Current WebCall source mapping:

- Room A: FOH-SQ7 flow 121 (`239.69.7.34:5004`), selecting Dante transmit
  channels 61-62 as one-based stream positions 5-6.
- Room B: the dedicated Q-SYS Room B stereo stream, using positions 1-2.
