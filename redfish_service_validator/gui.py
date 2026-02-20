# Copyright Notice:
# Copyright 2016-2026 DMTF. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/main/LICENSE.md

"""
Redfish Service Validator GUI

File : gui.py

Brief : This file contains the GUI to interact with the Redfish Service Validator
"""

import configparser
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog as tkFileDialog
import traceback
import webbrowser

import redfish_service_validator.redfish_logo as logo
import redfish_service_validator.console_scripts as rsv

g_config_file_name = "config/config.ini"

g_config_defaults = {
    "System Under Test": {
        "Service": {
            "value": "http://localhost:8000",
            "description": "The address of the Redfish service (with scheme)",
            "destination": "rhost",
        },
        "Username": {"value": "MyUser", "description": "The username for authentication", "destination": "user"},
        "Password": {"value": "MyPass", "description": "The password for authentication", "destination": "password"},
        "Authorization": {
            "value": "Session",
            "description": "The authorization type",
            "options": ["Basic", "Session"],
            "destination": "authtype",
        },
        "External HTTP Proxy": {
            "value": "",
            "description": "The URL of the HTTP proxy for accessing external sites",
            "destination": "ext_http_proxy",
        },
        "External HTTPS Proxy": {
            "value": "",
            "description": "The URL of the HTTPS proxy for accessing external sites",
            "destination": "ext_https_proxy",
        },
        "Service HTTP Proxy": {
            "value": "",
            "description": "The URL of the HTTP proxy for accessing the Redfish service",
            "destination": "serv_http_proxy",
        },
        "Service HTTPS Proxy": {
            "value": "",
            "description": "The URL of the HTTPS proxy for accessing the Redfish service",
            "destination": "serv_https_proxy",
        },
    },
    "Validator": {
        "Logs Directory": {
            "value": "logs",
            "description": "The directory for generated report files",
            "destination": "logdir",
        },
        "Schema Directory": {
            "value": "SchemaFiles",
            "description": "Directory for local schema files; default",
            "destination": "schema_directory",
        },
        "Mockup Directory": {
            "value": "",
            "description": "Path to directory containing mockups to override responses from the service",
            "destination": "mockup",
        },
        "Payload": {
            "value": "",
            "description": "Controls how much of the data model to test; see the README for details",
            "destination": "payload",
        },
        "Skip OEM": {
            "value": "False",
            "description": "Don't check OEM items",
            "options": ["True", "False"],
            "destination": "nooemcheck",
        },
        "Debugging": {
            "value": "False",
            "description": "Controls the verbosity of the debugging output",
            "options": ["True", "False"],
            "destination": "debugging",
        },
    },
}


class RSVGui:
    """
    Main class for the GUI

    Args:
        parent (Tk): Parent Tkinter object
    """

    def __init__(self, parent):
        # Set up the configuration
        self.config = {}
        for section in g_config_defaults:
            self.config[section] = {}
            for option in g_config_defaults[section]:
                self.config[section][option] = g_config_defaults[section][option]

        # Read in the config file, and apply any valid settings
        self.config_file = g_config_file_name
        self.system_under_test = tk.StringVar()
        self.parse_config()

        # Initialize the window
        self.parent = parent
        self.parent.title("Redfish Service Validator {}".format(rsv.tool_version))

        # Add the menu bar
        menu_bar = tk.Menu(self.parent)
        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Open Config", command=self.open_config)
        file_menu.add_command(label="Save Config", command=self.save_config)
        file_menu.add_command(label="Save Config As", command=self.save_config_as)
        file_menu.add_command(label="Edit Config", command=self.edit_config)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.parent.destroy)
        menu_bar.add_cascade(label="File", menu=file_menu)
        self.parent.config(menu=menu_bar)

        # Add the logo
        image = tk.PhotoImage(data=logo.logo)
        label = tk.Label(self.parent, image=image, width=384)
        label.image = image
        label.pack(side=tk.TOP)

        # Add the system under test label
        tk.Label(self.parent, textvariable=self.system_under_test, font=(None, 12)).pack(side=tk.TOP)

        # Add the buttons
        button_frame = tk.Frame(self.parent)
        button_frame.pack(side=tk.TOP, fill=tk.X)
        self.run_button_text = tk.StringVar()
        self.run_button_text.set("Run Test")
        self.run_button = tk.Button(button_frame, textvariable=self.run_button_text, command=self.run)
        self.run_button.pack(side=tk.LEFT)
        self.run_label_text = tk.StringVar()
        self.run_label_text.set("")
        tk.Label(button_frame, textvariable=self.run_label_text).pack(side=tk.LEFT)
        tk.Button(button_frame, text="Exit", command=self.parent.destroy).pack(side=tk.RIGHT)

    def update_sut(self):
        """
        Updates the System Under Test string
        """
        self.system_under_test.set("System Under Test: " + self.config["System Under Test"]["Service"]["value"])

    def parse_config(self):
        """
        Parses the configuration settings from a file
        """
        config_parser = configparser.ConfigParser()
        config_parser.optionxform = str
        config_parser.read(self.config_file)
        for section in config_parser.sections():
            for option in config_parser.options(section):
                if section in self.config:
                    if option in self.config[section]:
                        self.config[section][option]["value"] = config_parser.get(section, option)
        self.update_sut()

    def build_config_parser(self, preserve_case):
        """
        Builds a config parser element from the existing configuration

        Args:
            preserve_case (bool): True if the casing of the options is to be preserved

        Returns:
            ConfigParser: A ConfigParser object generated from the configuration data
        """
        config_parser = configparser.ConfigParser()
        if preserve_case:
            config_parser.optionxform = str
        for section in self.config:
            config_parser.add_section(section)
            for option in self.config[section]:
                config_parser.set(section, option, self.config[section][option]["value"])
        return config_parser

    def open_config(self):
        """
        Opens the configuration settings from a file
        """
        filename = tkFileDialog.askopenfilename(
            initialdir=os.getcwd(), title="Open", filetypes=(("INI", "*.ini"), ("All Files", "*.*"))
        )
        if filename == "":
            # User closed the box; just return
            return
        self.config_file = filename
        self.parse_config()

    def edit_config(self):
        """
        Edits the configuration settings
        """
        option_win = tk.Toplevel()
        option_win_frame = tk.Frame(option_win)
        option_win_canvas = tk.Canvas(option_win_frame)
        option_y_scroll = tk.Scrollbar(option_win_frame, orient="vertical", command=option_win_canvas.yview)
        option_y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        option_x_scroll = tk.Scrollbar(option_win, orient="horizontal", command=option_win_canvas.xview)
        option_x_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        option_win_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True)
        option_win_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        option_win_canvas.bind(
            "<Configure>", lambda e: option_win_canvas.configure(scrollregion=option_win_canvas.bbox("all"))
        )
        option_win_contents = tk.Frame(option_win_canvas)
        option_win_canvas.create_window((0, 0), window=option_win_contents)
        config_values = {}

        # Iterate through the config file options to build the window
        for section in self.config:
            config_values[section] = {}
            section_frame = tk.Frame(option_win_contents)
            section_frame.pack(side=tk.TOP)
            tk.Label(section_frame, text=section, anchor="center", font=(None, 16)).pack(side=tk.LEFT)
            for option in self.config[section]:
                option_frame = tk.Frame(option_win_contents)
                option_frame.pack(side=tk.TOP, fill=tk.X)
                tk.Label(option_frame, text=option, width=16, anchor="w").pack(side=tk.LEFT)
                config_values[section][option] = tk.StringVar()
                config_values[section][option].set(self.config[section][option]["value"])
                if "options" in self.config[section][option]:
                    option_menu = tk.OptionMenu(
                        option_frame, config_values[section][option], *self.config[section][option]["options"]
                    )
                    option_menu.configure(
                        width=26
                    )  # Need a better way to fine tune this so it lines up nicely with the text boxes; currently tuned for Windows
                    option_menu.pack(side=tk.LEFT)
                else:
                    tk.Entry(option_frame, width=32, textvariable=config_values[section][option]).pack(side=tk.LEFT)
                tk.Label(option_frame, text=self.config[section][option]["description"], anchor="w").pack(side=tk.LEFT)
        tk.Button(option_win_contents, text="Apply", command=lambda: self.apply_config(option_win, config_values)).pack(
            side=tk.BOTTOM
        )
        option_win_contents.update()
        option_win_canvas.config(
            xscrollcommand=option_x_scroll.set,
            yscrollcommand=option_y_scroll.set,
            width=option_win_contents.winfo_width(),
            height=option_win_contents.winfo_height(),
        )

    def apply_config(self, window, config_values):
        """
        Applies the configation settings from the edit window

        Args:
            window (Toplevel): Tkinter Toplevel object with text boxes to apply
            config_values (Array): An array of StringVar objects with the user input
        """
        for section in self.config:
            for option in self.config[section]:
                self.config[section][option]["value"] = config_values[section][option].get()
        self.update_sut()
        window.destroy()

    def save_config(self):
        """
        Saves the config file
        """
        config_parser = self.build_config_parser(True)
        with open(self.config_file, "w") as config_file:
            config_parser.write(config_file)

    def save_config_as(self):
        """
        Saves the config file as a new file
        """
        filename = tkFileDialog.asksaveasfilename(
            initialdir=os.getcwd(), title="Save As", filetypes=(("INI", "*.ini"), ("All Files", "*.*"))
        )
        if filename == "":
            # User closed the box; just return
            return
        self.config_file = filename
        if not self.config_file.lower().endswith(".ini"):
            self.config_file = self.config_file + ".ini"
        self.save_config()

    def run(self):
        """
        Runs the service validator
        """
        self.run_button_text.set("Running")
        self.run_button.config(state=tk.DISABLED)
        run_thread = threading.Thread(target=self.run_imp)
        run_thread.daemon = True
        run_thread.start()

    def run_imp(self):
        """
        Thread for running the service validator so the GUI doesn't freeze
        """
        self.run_label_text.set("Test running; please wait")

        run_window = tk.Toplevel()
        run_text_frame = tk.Frame(run_window)
        run_text_frame.pack(side=tk.TOP)
        run_scroll = tk.Scrollbar(run_text_frame)
        run_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        run_text = tk.Text(run_text_frame, height=48, width=128, yscrollcommand=run_scroll.set)
        sys.stdout = RunOutput(run_text)
        run_text.pack(side=tk.TOP)
        run_scroll["command"] = run_text.yview
        run_button_frame = tk.Frame(run_window)
        run_button_frame.pack(side=tk.BOTTOM)
        tk.Button(run_button_frame, text="OK", command=run_window.destroy).pack(side=tk.LEFT)
        tk.Button(run_button_frame, text="Copy", command=lambda: self.copy_text(run_text)).pack(side=tk.RIGHT)

        # Launch the validator
        try:
            args = {"collectionlimit": ["LogEntry", "20"]}
            for section in self.config:
                for option in self.config[section]:
                    if self.config[section][option]["value"] == "":
                        args[self.config[section][option]["destination"]] = None
                    elif self.config[section][option]["value"] == "True":
                        args[self.config[section][option]["destination"]] = True
                    elif self.config[section][option]["value"] == "False":
                        args[self.config[section][option]["destination"]] = False
                    else:
                        if option == "Payload":
                            args[self.config[section][option]["destination"]] = self.config[section][option][
                                "value"
                            ].split(" ")
                        else:
                            args[self.config[section][option]["destination"]] = self.config[section][option]["value"]
            status_code, last_results_page = rsv.run_validator(args)
            if last_results_page is not None:
                print(last_results_page)
                webbrowser.open_new(last_results_page)
            else:
                # The validation could not take place (for a controlled reason)
                notification_window = tk.Toplevel()
                tk.Label(notification_window, text="Test aborted", anchor="center").pack(side=tk.TOP)
                tk.Button(notification_window, text="OK", command=notification_window.destroy).pack(side=tk.BOTTOM)
        except:
            oops_window = tk.Toplevel()
            tk.Label(
                oops_window, text="Please copy the info below and file an issue on GitHub!", width=64, anchor="center"
            ).pack(side=tk.TOP)
            oops_text_frame = tk.Frame(oops_window)
            oops_text_frame.pack(side=tk.TOP)
            oops_scroll = tk.Scrollbar(oops_text_frame)
            oops_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            oops_text = tk.Text(oops_text_frame, height=32, width=64, yscrollcommand=oops_scroll.set)
            oops_text.insert(tk.END, traceback.format_exc())
            oops_text.pack(side=tk.TOP)
            oops_scroll["command"] = oops_text.yview
            oops_button_frame = tk.Frame(oops_window)
            oops_button_frame.pack(side=tk.BOTTOM)
            tk.Button(oops_button_frame, text="OK", command=oops_window.destroy).pack(side=tk.LEFT)
            tk.Button(oops_button_frame, text="Copy", command=lambda: self.copy_text(oops_text)).pack(side=tk.RIGHT)
        self.run_button.config(state=tk.NORMAL)
        self.run_button_text.set("Run Test")
        self.run_label_text.set("Test Complete")

    def copy_text(self, text):
        """
        Copies text to the system clipboard

        Args:
            text (Text): Tkinter Text object with text to copy
        """
        self.parent.clipboard_clear()
        self.parent.clipboard_append(text.get(1.0, tk.END))


class RunOutput(object):
    """
    Runtime output class

    Args:
        text (Text): Tkinter Text object to use as the output
    """

    def __init__(self, text):
        self.output = text

    def write(self, string):
        """
        Writes to the output object

        Args:
            string (string): The string to output
        """
        if self.output.winfo_exists():
            self.output.insert(tk.END, string)
            self.output.see(tk.END)

    def flush(self):
        """
        Flushes the output buffer
        """
        pass


def main():
    """
    Entry point for the GUI
    """
    root = tk.Tk()
    RSVGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
