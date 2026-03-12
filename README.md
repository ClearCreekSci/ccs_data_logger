# Clear Creek Scientific Data Logger

Provides a service to record  data from attached sensors. This software is designed to run on a Raspberry Pi. We use either the Pi Zero with wireless or the Pi Zero 2 with wireless.

# deployment directory
The deployment directory contains several scripts that create the zipped installation bundle from the development directory and later install the bundle on the target device. In order for the scripts to work correctly, the sensormods directory must be populated. To populate the sensormods directory, copy the desired sensor modules into the directory or create links there that point to the desired sensor modules.

# sensormods directory
For an ordinary installation, the sensormods directory contains Python scripts with a specific structure that read sensor data and communicate it back to the data station. We currently offer the following sensor module:

* [Adafruit BME280](https://github.com/ClearCreekSci/bme280_ccs_sensor)

TODO: Describe sensor module structure

