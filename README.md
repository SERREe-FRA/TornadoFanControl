# TornadoFanControl
Implements fan control on specific laptop models

### Supported models
- PHN16-72

## About
CPP backend for low cpu usage and low consumption, Python for gui.

The cpp code automaticaly starts with windows and uses the EC(embedded controller) for temperature readout and fan control.

## Usage
Install the module in dist\TornadoFanControllerInstaller.exe and reboot.

You can still use ACER PredatorSense and mode switching, the app wil only try to overwrite the current fan speed based of temperatures.

Editing the fan profile is possible with a simple ui.
