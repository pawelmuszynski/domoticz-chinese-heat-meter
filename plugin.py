#!/usr/bin/env python


"""
Chineese Heat Meter. The Python plugin for Domoticz
Author: pawelmuszynski
GitHub: https://github.com/pawelmuszynski/domoticz-chinese-heat-meter-plugin
Requirements:
    1.Communication module MBUS (Meter Bus) to USB converter. This is not Modbus.
"""
"""
<plugin key="chinese-heat-meter" name="Chinese Heat Meter" version="0.0.1" author="pawelmuszynski">
    <params>
        <param field="SerialPort" label="MBUS Port" width="200px" required="true" default="/dev/ttyUSB0" />
        <param field="Mode1" label="Reading Interval sec." width="40px" required="true" default="60" />
        <param field="Mode6" label="Debug" width="75px">
            <options>
                <option label="True" value="Debug" />
                <option label="False" value="Normal" default="true" />
            </options>
        </param>
    </params>
</plugin>
"""


import serial
import Domoticz

class ChineseHeatMeter:
    def __init__(self, ser):
        self.serial = ser
        self.response = bytearray()
        self.cooling_energy = 0
        self.heating_energy = 0
        self.heating_power = 0
        self.flow_rate = 0
        self.flow = 0
        self.heating_temp = 0
        self.return_temp = 0
        self.working_hours = 0

    def __del__(self):
        self.serial.close()

    def _verify_header_and_tail(self):
        return self.response[0].to_bytes(1, byteorder="big") == b'\x68' and self.response[58].to_bytes(1, byteorder="big") == b'\x16'

    def _verify_data_integrity(self):
        return (sum(self.response[0:56]) & 0xFF).to_bytes(1, byteorder="big") == self.response[57].to_bytes(1, byteorder="big")

    def _verify_response(self):
        return self._verify_header_and_tail() and self._verify_data_integrity()

    @staticmethod
    def _bcd_to_int(bcd):
        result = 0
        fastDict = {16 * (i // 10) + (i % 10): i for i in range(100)}
        while bcd and bcd[0] in fastDict:
            result *= 100
            result += fastDict[bcd[0]]
            bcd = bcd[1:]
        if bcd and bcd[0] & 0xf0 <= 0x90:
            result *= 10
            result += bcd[0]>>4
            if bcd[0] & 0xf <= 9:
                result *= 10
                result += bcd[0] & 0x0f
        return result

    def get_values(self):
        header = bytearray(b'\x68')
        device_type = bytearray(b'\x20')
        device_address = bytearray(b'\xaa\xaa\xaa\xaa\xaa\xaa\xaa')
        control_code = bytearray(b'\x01')
        data = bytearray(b'\x1f\x90\x00')
        data_length = bytearray(len(data).to_bytes(1, byteorder="big"))
        frame = header + device_type + device_address + control_code + data_length + data
        checksum = bytearray((sum(frame) & 0xFF).to_bytes(1, byteorder="big"))
        tail = bytearray(b'\x16')
        frame += checksum + tail
        self.serial.write(frame)
        raw_response = self.serial.read(59)
        self.serial.flush()
        self.response = bytearray(raw_response)
        if not self._verify_response():
            raise Exception("Wrong frame received")
        self.cooling_energy = ChineseHeatMeter._bcd_to_int(bytes(reversed(self.response[14:17])))
        self.heating_energy = ChineseHeatMeter._bcd_to_int(bytes(reversed(self.response[19:22])))
        self.heating_power = ChineseHeatMeter._bcd_to_int(bytes(reversed(self.response[24:27])))
        self.flow_rate = ChineseHeatMeter._bcd_to_int(bytes(reversed(self.response[29:32])))
        self.flow = ChineseHeatMeter._bcd_to_int(bytes(reversed(self.response[34:37])))
        self.heating_temp = ChineseHeatMeter._bcd_to_int(bytes(reversed(self.response[39:41])))
        self.return_temp = ChineseHeatMeter._bcd_to_int(bytes(reversed(self.response[42:44])))
        self.working_hours = ChineseHeatMeter._bcd_to_int(bytes(reversed(self.response[45:47])))


class BasePlugin:
    def __init__(self):
        self.run_interval = 0
        self.heat_meter = None
        return

    def onStart(self):
        Domoticz.Log("Chinese Heat Meter plugin starting")
        ser = serial.Serial(Parameters["SerialPort"], 2400, serial.EIGHTBITS, serial.PARITY_EVEN, serial.STOPBITS_ONE, 1)
        self.heat_meter = ChineseHeatMeter(ser)
        self.run_interval = int(Parameters["Mode1"]) / 10
        if 1 not in Devices:
            Domoticz.Device(Name="Cooling Energy", Unit=1, Type=113, Switchtype=0, Used=0).Create()
        if 2 not in Devices:
            Domoticz.Device(Name="Heating Energy", Unit=2, Type=113, Switchtype=0, Used=0).Create()
        if 3 not in Devices:
            Domoticz.Device(Name="Heating Power", Unit=3, TypeName="Usage", Used=1).Create()
        if 4 not in Devices:
            Domoticz.Device(Name="Flow Rate", Unit=4, TypeName="Custom", Used=1, Options={ "Custom": "1;Flowrate (m³/h)" }).Create()
        if 5 not in Devices:
            Domoticz.Device(Name="Flow", Unit=5, Type=113, Switchtype=2, Used=0).Create()
        if 6 not in Devices:
            Domoticz.Device(Name="Heating Temperature", Unit=6, TypeName="Temperature", Used=1).Create()
        if 7 not in Devices:
            Domoticz.Device(Name="Return Temperature", Unit=7, TypeName="Temperature", Used=1).Create()
        if 8 not in Devices:
            Domoticz.Device(Name="Working Hours", Unit=8, Type=113, Switchtype=3, Used=0, Options={ "ValueQuantity": "Time (h)", "ValueUnits": "h" }).Create()

        Domoticz.Log("Chinese Heat Meter plugin started")

    def onStop(self):
        Domoticz.Log("Chinese Heat Meter plugin stop")
        self.heat_meter = None

    def onHeartbeat(self):
        self.run_interval -= 1
        if self.run_interval <= 0:
            # Get data from Chinese Heat Meter
            try:
                self.heat_meter.get_values()
            except:
                Domoticz.Log("Error to read device");
            else:
                # Update devices
                Devices[1].Update(0, str(self.heat_meter.cooling_energy * 10))  # Wh
                Devices[2].Update(0, str(self.heat_meter.heating_energy * 10))  # Wh
                Devices[3].Update(0, str(self.heat_meter.heating_power * 10))  # W
                Devices[4].Update(0, str(self.heat_meter.flow_rate / 10000))  # m³/h
                Devices[5].Update(0, str(self.heat_meter.flow * 100))  # L
                Devices[6].Update(0, str(self.heat_meter.heating_temp / 100))  # °C
                Devices[7].Update(0, str(self.heat_meter.return_temp / 100))  # °C
                Devices[8].Update(0, str(self.heat_meter.working_hours))  # h

                if Parameters["Mode6"] == 'Debug':
                    Domoticz.Log("Chinese Heat Meter Data")
                    Domoticz.Log('Cooling Energy: {0:.2f} kWh'.format(self.heat_meter.cooling_energy / 100))
                    Domoticz.Log('Heating Energy: {0:.2f} kWh'.format(self.heat_meter.heating_energy / 100))
                    Domoticz.Log('Heating Power: {0:.2f} kW'.format(self.heat_meter.heating_power / 100))
                    Domoticz.Log('Flow Rate: {0:.3f} m³/h'.format(self.heat_meter.flow_rate / 10000))
                    Domoticz.Log('Flow: {0:.3f} m³'.format(self.heat_meter.flow))
                    Domoticz.Log('Heating Temperature: {0:.2f} °C'.format(self.heat_meter.heating_temp / 100))
                    Domoticz.Log('Return Temperature: {0:.2f} °C'.format(self.heat_meter.return_temp / 100))
                    Domoticz.Log('Working Hours: {:d} h'.format(self.heat_meter.working_hours))
            self.run_interval = int(Parameters["Mode1"]) / 10

global _plugin
_plugin = BasePlugin()


def onStart():
    global _plugin
    _plugin.onStart()


def onStop():
    global _plugin
    _plugin.onStop()


def onHeartbeat():
    global _plugin
    _plugin.onHeartbeat()
