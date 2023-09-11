The `ascaso_dose_weight` project is a Python program designed to control an espresso machine. It utilizes a Raspberry Pi, a 1.3 inch LCD screen, and a touch screen interface to interact with the user. The program allows the user to set a target weight for their espresso shot, and it will automatically stop the shot once the target weight is reached.

## How does it work?
The program utilizes a touch screen interface to handle user input. The user can set the desired weight for their espresso shot, and the program will display the current weight and shot time on the LCD screen. The program uses a Bluetooth Low Energy (BLE) connection to communicate with a scale that measures the weight of the shot.

When the user starts a shot, the program will activate a relay that controls the espresso machine. It will also start a timer to keep track of the shot time. The program continuously reads the weight from the scale and updates the LCD screen. Once the target weight is reached, the program will stop the shot by deactivating the relay.

## How to use it?
To use the `ascaso_dose_weight` program, you will need a Raspberry Pi, a 1.3 inch LCD screen, a touch screen interface, and a compatible scale. You will also need to install the required Python libraries and dependencies.

Once you have all the necessary hardware and software set up, you can run the `main.py` program on your Raspberry Pi. The program will display the current weight and shot time on the LCD screen. You can use the touch screen interface to set the desired weight for your espresso shot and start the shot. The program will automatically stop the shot once the target weight is reached.

## Configuration
The program uses a YAML file, `settings.yaml`, to store the target weight for the espresso shot. If the file doesn't exist, the program will create it and use a default value of 35 grams. You can manually edit the YAML file to change the target weight.

## Dependencies
The `ascaso_dose_weight` program requires several Python libraries and dependencies. These include:
- `RPi.GPIO`: A Python library for controlling the Raspberry Pi's GPIO pins.
- `bluepy`: A Python library for BLE communication.
- `PIL`: The Python Imaging Library, used for image processing.
- `PyYAML`: A Python library for working with YAML files.

You can install these dependencies using pip:
```
pip install RPi.GPIO bluepy pillow pyyaml
```

## Contributing
If you would like to contribute to the `ascaso_dose_weight` project, you can submit pull requests on the GitHub repository. Please make sure to follow the code style guidelines and provide clear descriptions of your changes.

## License
The `ascaso_dose_weight` project is licensed under the MIT License. You can find a copy of the license in the `LICENSE` file.