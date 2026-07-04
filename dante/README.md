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
