# Copyright Notice:
# Copyright 2016 Distributed Management Task Force, Inc. All rights reserved.
# License: BSD 3-Clause License. For full text see link: https://github.com/DMTF/Redfish-Service-Validator/blob/master/LICENSE.md

"""
Redfish Service Validator GUI

File : RedfishServiceValidatorGui.py

Brief : This file contains the GUI to interact with the RedfishServiceValidator
"""

import configparser
import sys
import threading
import tkinter as tk
import traceback
import webbrowser

import RedfishServiceValidator as rsv

config_file_name = "config.ini"

class RSVGui:
    """
    Main class for the GUI

    Args:
        parent (tkinter): Parent Tkinter object
    """

    def __init__( self, parent ):
        # Read in the config file
        self.config = configparser.ConfigParser()
        self.config.optionxform = str
        file_names = self.config.read( config_file_name )
        if len( file_names ) == 0:
            # No config file; create default configuration
            self.config.add_section( "SystemInformation" )
            self.config.set( "SystemInformation", "TargetIP", "127.0.0.1:8000" )
            self.config.set( "SystemInformation", "SystemInfo", "Test Config, place your own description of target system here" )
            self.config.set( "SystemInformation", "UserName", "xuser" )
            self.config.set( "SystemInformation", "Password", "xpasswd" )
            self.config.set( "SystemInformation", "AuthType", "None" )
            self.config.set( "SystemInformation", "Token", "" )
            self.config.set( "SystemInformation", "UseSSL", "False" )
            self.config.set( "SystemInformation", "CertificateCheck", "False" )
            self.config.set( "SystemInformation", "CertificateBundle", "" )
            self.config.add_section( "Options" )
            self.config.set( "Options", "MetadataFilePath", "./SchemaFiles/metadata" )
            self.config.set( "Options", "CacheMode", "Off" )
            self.config.set( "Options", "CacheFilePath", "" )
            self.config.set( "Options", "SchemaSuffix", "_v1.xml" )
            self.config.set( "Options", "Timeout", "30" )
            self.config.set( "Options", "HttpProxy", "" )
            self.config.set( "Options", "HttpsProxy", "" )
            self.config.set( "Options", "LocalOnlyMode", "False" )
            self.config.set( "Options", "ServiceMode", "False" )
            self.config.set( "Options", "LinkLimit", "LogEntry:20" )
            self.config.set( "Options", "Sample", "0" )
            self.config.add_section( "Validator" )
            self.config.set( "Validator", "PayloadMode", "Default" )
            self.config.set( "Validator", "PayloadFilePath", "" )
            self.config.set( "Validator", "LogPath", "./logs" )

        # Initialize the window
        self.parent = parent
        self.parent.title( "Redfish Service Validator {}".format( rsv.tool_version ) )
        self.config_item_label = {}
        self.config_item_box = {}

        # Iterate through the config file options to build the window
        for section in self.config.sections():
            self.config_item_box[section] = {}
            section_frame = tk.Frame( self.parent )
            section_frame.pack( side = tk.TOP )
            section_label = tk.Label( section_frame, text = section, width = 64, anchor = "center" )
            section_label.pack( side = tk.LEFT )
            for option in self.config.options( section ):
                option_frame = tk.Frame( self.parent )
                option_frame.pack( side = tk.TOP )
                option_label = {}
                option_label = tk.Label( option_frame, text = option, width = 16, anchor = "w" )
                option_label.pack( side = tk.LEFT )
                self.config_item_box[section][option] = tk.Entry( option_frame, width = 48 )
                self.config_item_box[section][option].insert( tk.END, self.config.get( section, option ) )
                self.config_item_box[section][option].pack( side = tk.LEFT )

        # Add the buttons
        button_frame = tk.Frame( self.parent )
        button_frame.pack( side = tk.TOP, fill = tk.X )
        button = tk.Button( button_frame, text = "Save Config", command = self.save_config )
        button.pack( side = tk.LEFT )
        self.run_button_text = tk.StringVar()
        self.run_button_text.set( "Run Test" )
        self.run_button = tk.Button( button_frame, textvariable = self.run_button_text, command = self.run )
        self.run_button.pack( side = tk.LEFT )
        self.run_label_text = tk.StringVar()
        self.run_label_text.set( "" )
        self.run_label = tk.Label( button_frame, textvariable = self.run_label_text )
        self.run_label.pack( side = tk.LEFT )
        button = tk.Button( button_frame, text = "Exit", command = self.parent.destroy )
        button.pack( side = tk.RIGHT )

    def save_config( self ):
        """
        Saves the config file
        """
        for section in self.config_item_box:
            for option in self.config_item_box[section]:
                self.config.set( section, option, self.config_item_box[section][option].get() )
        with open( config_file_name, "w" ) as config_file:
            self.config.write( config_file )

    def run( self ):
        """
        Runs the service validator
        """
        # Save the config file
        self.save_config()
        self.run_button_text.set( "Running" )
        self.run_button.config( state = tk.DISABLED )

        run_thread = threading.Thread( target = self.run_imp )
        run_thread.daemon = True
        run_thread.start()

    def run_imp( self ):
        """
        Thread for running the service validator so the GUI doesn't freeze
        """
        self.run_label_text.set( "Test running; please wait" )

        # Launch the validator
        try:
            rsv_config = configparser.ConfigParser()
            rsv_config.read( config_file_name )
            status_code, last_results_page = rsv.main( rsv_config )
            if last_results_page != None:
                webbrowser.open_new( last_results_page )
        except:
            oops_window = tk.Toplevel()
            oops_label = tk.Label( oops_window, text = "Please copy the info below and file an issue on GitHub!", width = 64, anchor = "center" )
            oops_label.pack( side = tk.TOP )
            oops_text_frame = tk.Frame( oops_window )
            oops_text_frame.pack( side = tk.TOP )
            oops_scroll = tk.Scrollbar( oops_text_frame )
            oops_scroll.pack( side = tk.RIGHT, fill = tk.Y )
            oops_text = tk.Text( oops_text_frame, height = 32, width = 64, yscrollcommand = oops_scroll.set )
            oops_text.insert( tk.END, traceback.format_exc() )
            oops_text.pack( side = tk.TOP )
            oops_button_frame = tk.Frame( oops_window )
            oops_button_frame.pack( side = tk.BOTTOM )
            oops_ok = tk.Button( oops_button_frame, text = "OK", command = oops_window.destroy )
            oops_ok.pack( side = tk.LEFT )
            oops_copy = tk.Button( oops_button_frame, text = "Copy", command = lambda: self.copy_text( oops_text ) )
            oops_copy.pack( side = tk.RIGHT )
        self.run_button.config( state = tk.NORMAL )
        self.run_button_text.set( "Run Test" )
        self.run_label_text.set( "Test Complete" )

    def copy_text( self, text ):
        """
        Copies text to the system clipboard

        Args:
            text (Text): Tkinter Text object with text to copy
        """
        self.parent.clipboard_clear()
        self.parent.clipboard_append( text.get( 1.0, tk.END ) )

def main():
    """
    Entry point for the GUI
    """
    root = tk.Tk()
    gui = RSVGui( root )
    root.mainloop()

if __name__ == '__main__':
    main()
