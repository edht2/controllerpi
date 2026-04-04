from app.config.config import state, temperature_range_play
from app.tools.calculate_vpd import calculate_vpd
from app.tools.percent_range import percent_range
from app.tools.log import log
from app.control.actuator import Actuator
from app.control.solenoid import Solenoid
from app.control.windows import WindowGroup
#from lib.weather.client import Client as Weather_Client
from app.mqtt.mqtt import sub
from app.bed import Bed
from json import load

class ClimateZone:
    
    def __init__(self, climate_zone_number: int) -> None:
        
        self.climate_zone_number = climate_zone_number
        
        # *** Sensor Values ***
        self.temperature = None
        self.relative_humidity = None
        self.vapour_pressure_defecit = None
        self.co2_ppm = None
        
        self.values_set = False
        # *********************
               
        # ******** Beds *******
        self.beds = [
            Bed(self.climate_zone_number, bed["bedNumber"]) 
            for bed in state[self.climate_zone_number-1]["Beds"]]
        # get all of the beds and create a bed object for each one
        log('OK', f'climatezone{self.climate_zone_number}', 'init', 'All beds initialised successfuly')
        # *********************

        # * Climate Solenoids *
        self.heating_solenoid = Solenoid(state[self.climate_zone_number-1]["heatingSolenoidRelayIndex"])
        self.misting_solenoid = Solenoid(state[self.climate_zone_number-1]["mistingSolenoidRelayIndex"])
        # *********************
        
        # ****** Windows ******
        self.top_windows = WindowGroup('topWindows', self.climate_zone_number)
        self.side_windows = WindowGroup('sideWindows', self.climate_zone_number)
        # create new window instance
        log('OK', f'climatezone{self.climate_zone_number}', 'init', 'Window acctuators initialised')
        # *********************
        
        # *** SensorPi Data ***
        sub().subscribe(f'climate_zone_{self.climate_zone_number}', self.on_sensor_update)
        # subscribe to climate zone data
        # *********************
        
        log('OK', f"climatezone{self.climate_zone_number}", "init", f"Successfuly initialised climate-zone")
        # log the climate-zone has been created!
        
        
    def on_sensor_update(self, data: str) -> None:
        # When a data packet gets recived from the sensor pi
        
        data = load(data)
        # turn json string into python dictionary
        
        self.temperature = data['median_temp']
        self.relative_humidity = data['median_rh']
        self.co2_ppm = data['median_co2_ppm']
        
        self.vapour_pressure_defecit = calculate_vpd(self.relative_humidity)
        # set the sensor variables  
        
        if not self.values_set:
            self.values_set = True
        # used for quick verification
        
        
    def extreme_correction(self, state: dict) -> bool:
        """ Corrects the green-house's windows, heating and misting in the event that temperature, VPD or CO2 get out of the
        extreme ranges. This will use an 'extreme priority' based solution. Where if a value is out-side of the extreme
        range it is completly prioritised - everything else is dropped, to be fixed even if that means it will cause another problem soon. """
        
        if self.temperature < state['climateZones'][self.climate_zone_number-1]['extremeTemperatureRange'][0]:
            # the greenhouse is way too cold!!! Emergency mode, drop everything and do everying
            self.top_windows.close()
            self.side_windows.close()
            self.misting_solenoid.close()
            self.heating_solenoid.open()
            return True
        
        if self.temperature > state['climateZones'][self.climate_zone_number-1]['extremeTemperatureRange'][1]:
            # the greenhouse is way too hot!!!
            self.top_windows.open()
            self.side_windows.open()
            self.misting_solenoid.open()
            self.heating_solenoid.close()
            return True
        
        if self.vapour_pressure_defecit < state['climateZones'][self.climate_zone_number-1]['extremeVPDRange'][0]:
            # the green-house is way too damp!!!
            self.top_windows.open()
            self.side_windows.open()
            self.misting_solenoid.close()
            self.heating_solenoid.close()
            return True
        
        if self.vapour_pressure_defecit > state['climateZones'][self.climate_zone_number-1]['extremeVPDRange'][1]:
            # the green-house is way too dry / arid!!!
            self.top_windows.close()
            self.side_windows.close()
            self.misting_solenoid.open()
            self.heating_solenoid.close()
            return True
            
        if self.co2_ppm < state['climateZones'][self.climate_zone_number-1]['minimumExtremeCO2ppm']:
            # if CO2 is too low for proper operation ↓
            self.top_windows.open()
            self.side_windows.open()
            # CO2 enrichment (boiler room fan)
            return True
        
        return False
    
        
    def update(self) -> None:
    
        for bed in self.beds:
            # for every bed do an update
            bed.update()
        
        if not self.values_set:
            # sensor data hasn't been recived yet! So no climate optimisation can occur
            log("WARN", f"climatezone{self.climate_zone_number}", "update", "No sensor data")
            return None
        
        state = load(open("app/config/state.json"))["climateZones"]
        # reload state incase there were any changes to the ranges and targets

        if self.extreme_correction(state): return None
        # correct any extremities
        
        # find the percent of the range the temp and vpd are
        normalised_temp = percent_range(state['climateZones'][self.climate_zone_number-1]['targetTemperatureRange'], self.temperature)
        normalised_vpd = percent_range(state['climateZones'][self.climate_zone_number-1]['targetVPDRange'], self.vapour_pressure_defecit)
        
        """ *** CLIMATE CONTROL ***
        The greenhouse uses a priority based system to optimise the climate. Temperature is prioritised then humidity and finally CO₂. Extremities of the ranges are dealt with first """
        
        # *** Extremes of ranges ***    
        if normalised_temp >= 90:
            # if the climate-zone is above 90% heat, yikes!
            self.top_windows.open()
            self.side_windows.open()
            self.misting_solenoid.open()
            self.heating_solenoid.close()
            return
        
        if normalised_temp <= 10:
            # if the climate zone is below 10%. COLD!
            self.top_windows.close()
            self.side_windows.close()
            self.misting_solenoid.close()
            self.heating_solenoid.open()
            return
        
        if normalised_vpd >= 90:
            # if the climate-zone is above 90% VPD
            self.top_windows.close()
            self.side_windows.close()
            self.misting_solenoid.open()
            self.heating_solenoid.close()
            return
        
        if normalised_vpd <= 10:
            # if the climate zone is below 10% VPD
            self.top_windows.open()
            self.side_windows.open()
            self.misting_solenoid.close()
            self.heating_solenoid.close()
            return
        
        # *** Minor ajustments ***
        if normalised_temp >= 75 and normalised_temp < 90:
            # if the climate-zone is at 75% heat
            self.top_windows.open()
            self.side_windows.open()
            self.misting_solenoid.close()
            self.heating_solenoid.close()
            return
        
        if normalised_temp <= 25 and normalised_temp > 10:
            # if the climate zone is between 25% and 10% heat; so coldish
            self.top_windows.close()
            self.side_windows.close()
            self.misting_solenoid.close()
            self.heating_solenoid.close()
            return
        
        if normalised_vpd >= 75 and normalised_vpd < 90:
            # if the climate-zone is at 75% vpd
            self.top_windows.close()
            self.side_windows.close()
            self.misting_solenoid.close()
            self.heating_solenoid.open()
            return
            
        if normalised_vpd <= 25 and normalised_vpd > 10:
            # if the climate zone is between 25% and 10% vpd
            self.top_windows.close()
            self.side_windows.open()
            self.misting_solenoid.close()
            self.heating_solenoid.close()
            return
        
        # *** CARBON DIOXIDE CONTROL (lowest priority) ***
        if self.co2_ppm < state['climateZones'][self.climate_zone_number-1]['minimumTargetCO2ppm']:
            # if the CO₂ ppm is less than the target minimum level and the temperature and VPD are OK open the windows
            # only opening side windows to reduce heat loss
            self.side_windows.open()
            #self.boiler_fan.enable()