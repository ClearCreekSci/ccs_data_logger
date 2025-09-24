# Clear Creek Scientific Weather Data Logger

Provides a service to record  data from attached sensors. This software is designed to run on a Raspberry Pi. We use either the Pi Zero with wireless or the Pi Zero 2 with wireless.

# deployment directory
The deployment directory contains several scripts that create the zipped installation bundle from the development directory and later install the bundle on the target device. In order for the scripts to work correctly, the plugins directory must be populated. To populate the plugins directory, copy the desired plugins into the directory or create links there that point to the desired plugins.

# plugins directory
For an ordinary installation, the plugins directory contains Python scripts with a specific structure that read sensor data and communicate it back to the data station. We currently offer the following plugins:

* [Adafruit BME280](https://github.com/ClearCreekSci/bme280_ccs_plugin)

TODO: Describe plugin structure

