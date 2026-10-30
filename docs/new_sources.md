## Weather

### Normal Weather: NWS AFDs \+ GHCN-H Data

* **Text:** Multi-paragraph write-ups by duty meteorologists at each of the NWS's 122 local forecast offices, issued several times a day.   
* **TS:** Hourly readings from airport weather stations (temperature, dew point, wind, rainfall), which matches MTBench's current weather setup.  
* **Why the text adds signal:** Text explains what the forecaster expects over roughly the next week and why. Example: "a 50 to 80 percent chance of seeing an inch of rain."  
* **Alignment:** Every office covers a known area, so its text maps to the stations inside it. The issue time marks the end of the input window, and section headers give the horizon (e.g., "Saturday through Wednesday"). 

### Cyclones: NHC Tropical Cyclone Discussions \+ HURDAT2 best track 

* **Text:** For each active tropical storm, a forecaster-written explanation every 6 hours of where it is heading and how strong it will get, with the reasoning (wind shear, ocean temperature, model disagreement) and a forecast table out to 5 days.  
* **Time series:** HURDAT2 – the official record of each storm's position, top wind speed, and pressure every 6 hours.  
* **Why the text adds signal:** Forecaster-written rationale provides reasoning for the tropical storm’s predicted future behavior.  
* **Alignment:** Align text and TS based on their same storm ID and 6-hourly timestamps.

### Space Weather: NOAA SWPC Forecast Discussion \+ Kp Index 

* **Text:** Space Weather Prediction Center (SWPC) Forecast Discussions from the National Oceanic and Atmospheric Administration Home (NOAA) are forecaster-written rationale predicting how disturbed Earth's magnetic field will be over the next 3 days, driven by activity on the Sun.  
* **Time series:** Kp, a 0–9 score reported every 3 hours. Kp 5 or higher counts as a geomagnetic storm.  
* **Why text adds signal:** Forecasters see solar imagery of eruptions and hot spots 1–4 days before their effects reach Earth. Kp's own history cannot show that.  
* **Alignment:** Kp is one global number, so no location matching is needed. The forecast is issued at a known UTC time and covers 8 three-hour bins per day for 3 days. 

### Floods and Storms: Hydrology and River Flood Monitoring

* **Text Content:** NWS Flood Warnings, Flood Statements, and Storm Events Database entries describing heavy upstream rain, ground absorption capacity, and predicted river crest levels.

* **TS:** Continuous 15-minute river gauge measurements from thousands of USGS sensors tracking water level height (stage) and flow volume (discharge).  
* **Why text adds signal:** There’s a delayed causal link between the text and TS — heavy rainfall reported upstream takes hours or days to travel down river basins. Text warnings predict downstream flooding before local river gauges physically record rising water levels.  
* **Alignment:** Link TS+text by matching specific river gauge names in flood warning texts to USGS gauge numbers using watershed topology mapping.

## Economics

### Macroeconomics: FOMC Documents \+ Macroeconomic Rates

* **Text:** Written meeting minutes and economic summaries published by the Federal Open Market Committee (FOMC) in their Summary of Economic Projections (SEP)  
* **TS:** Quarterly projected numbers for interest rates, Gross Domestic Product (GDP) growth, Personal Consumption Expenditures (PCE) inflation, and unemployment rates  
* **Why text adds signal:** The TS shows *what* is expected in the future, but the text explains *why* central bank officials changed their minds (e.g., such as unexpected labor market pressures or persistent inflation in core services).  
* **Alignment:** Text and TS are published together four times per year. Alignment is verified by matching target numbers cited in the report text against official release records in the FRED database.

### Agriculture: Agricultural Crops and Global Food Supply

* **Text Content:** Monthly text summaries from the World Agricultural Supply and Demand Estimates (WASDE) report analyzing crop growing conditions, international trade policies, and harvest pacing.  
* **TS:** Monthly balance sheet metrics tracking crop production volumes, global import/export totals, remaining crop inventory (ending stocks), and average farm sale prices.  
* **Why text adds signal:** Production numbers alone do not explain sudden inventory drops. The text explains underlying causes, such as regional drought progression or foreign trade tariffs.  
* **Alignment:** Pair TS+text using monthly report bulletin numbers and crop marketing years. 

## 

## Finance

### Haiwen’s Multimodal Stock Dataset

* **Text Content:** News articles   
* **TS:** Stock returns   
* **Why text adds signal:** Provides context on real-world events that may affect how the market behaves – this context can’t be recovered from TS   
* **Alignment:** Already aligned

## Energy

### Energy Markets and Power Grid Operations

* **Text:**   
  * *EIA Short-Term Energy Outlook (STEO):* Monthly analysis covering global oil, natural gas, and electricity market trends.  
  * *Grid Operations Alerts:* Real-time market notices, Energy Emergency Alerts (EEA), CAISO Flex Alerts, and DOE OE-417 emergency outage descriptions (e.g., during major events like Winter Storm Uri).  
* **TS:** Monthly energy prices and stock levels (EIA), national hourly electricity demand (EIA-930), and real-time regional power demand, generation capacity, and wholesale electricity prices.  
* **Why text adds signal:** Real-time electricity prices can jump 100x during grid crises. Operational alerts describe physical generator failures, severe cold snaps, and emergency fuel orders that explain these massive price spikes. Alerts also include "busted" cases where emergency warnings were issued but outages were successfully avoided.  
* **Alignment:** Link TS+text using regional grid operator identifiers and exact issuance timestamps. 

## Transportation

### Aviation Operations and Flight Delays

* **Text Content:** Real-time operational messages issued by the Air Traffic Control System Command Center (ATCSCC) explaining flight restrictions, ground stops, and airport delay expectations.  
* **TS:** Airport operational data recorded every 15 minutes, tracking flight arrival delays, taxiing wait times, and flight volume counts.  
* **Why text adds signal**: Flight delay statistics *how much* the planes will be late, but the text explains *why* — such as severe thunderstorm corridors or local runway closures.  
* **Alignment**: Link TS+text using four-letter airport location codes (International Civil Aviation Organization identifiers like LGA for New York LaGuardia) and advisory timestamps.

## Healthcare

### Public Health and Disease Surveillance

* **Text Content:** Weekly narrative overviews from the FluView report detailing seasonal flu spread, regional severity levels, and virus strain characteristics.  
* **TS:** Weekly percentages of outpatient doctor visits for flu-like illness (ILINet data) and laboratory test positivity counts.  
* **Why text adds signal:** Infection numbers track outbreak size, but text supplies *qualitative biological context* (e.g., whether circulating virus strains match current seasonal vaccines).  
* **Alignment:** Pair TS+text using standardized calendar week numbers (Morbidity and Mortality Weekly Report weeks).

##### Detailed List

1. **Normal Weather: NWS AFDs \+ GHCN-H Data**   
   1. **Text:** Multi-paragraph write-ups by duty meteorologists at each of the NWS's 122 local forecast offices, issued several times a day.   
   2. **TS:** Hourly readings from airport weather stations (temperature, dew point, wind, rainfall), which matches MTBench's current weather setup.  
   3. **Why the text adds signal:** Text explains what the forecaster expects over roughly the next week and why. Example: "a 50 to 80 percent chance of seeing an inch of rain."  
2. **Cyclones: NHC Tropical Cyclone Discussions \+ HURDAT2 best track**   
   1. **Text:** For each active tropical storm, a forecaster-written explanation every 6 hours of where it is heading and how strong it will get, with the reasoning (wind shear, ocean temperature, model disagreement) and a forecast table out to 5 days.  
   2. **Time series:** HURDAT2 – the official record of each storm's position, top wind speed, and pressure every 6 hours.  
   3. **Why the text adds signal:** Forecaster-written rationale provides reasoning for the tropical storm’s predicted future behavior.  
3. **Geomagnetic Activity: NOAA SWPC Forecast Discussion \+ Kp Index**  
   1. **Text:** Space Weather Prediction Center (SWPC) Forecast Discussions from the National Oceanic and Atmospheric Administration Home (NOAA) are  
   2. **Time series:** Planetary Kp index –  a global 0-9 scale that measures geomagnetic activity and solar storm intensity  
   3. **Why text adds signal:** Forecasters see solar imagery of eruptions and hot spots 1-4 days before their effects reach Earth – Kp's own history cannot show that.  
4. **Floods and Storms: Hydrology and River Flood Monitoring**  
   1. **Text Content:** NWS Flood Warnings, Flood Statements, and Storm Events Database entries describing heavy upstream rain, ground absorption capacity, and predicted river crest levels.  
   2. **TS:** Continuous 15-minute river gauge measurements from thousands of USGS sensors tracking water level height (stage) and flow volume (discharge).  
   3. **Why text adds signal:** There’s a delayed causal link between the text and TS — heavy rainfall reported upstream takes hours or days to travel down river basins. Text warnings predict downstream flooding before local river gauges physically record rising water levels.  
5. Macroeconomics: FOMC Documents \+ Macroeconomic Rates  
   1. **Text:** Written meeting minutes and economic summaries published by the Federal Open Market Committee (FOMC) in their Summary of Economic Projections (SEP)  
   2. **TS:** Quarterly projected numbers for interest rates, Gross Domestic Product (GDP) growth, Personal Consumption Expenditures (PCE) inflation, and unemployment rates  
   3. **Why text adds signal:** The TS shows *what* is expected in the future, but the text explains *why* central bank officials changed their minds (e.g., such as unexpected labor market pressures or persistent inflation in core services).  
6. Agriculture: Agricultural Crops and Global Food Supply  
   1. **Text Content:** Monthly text summaries from the World Agricultural Supply and Demand Estimates (WASDE) report analyzing crop growing conditions, international trade policies, and harvest pacing.  
   2. **TS:** Monthly balance sheet metrics tracking crop production volumes, global import/export totals, remaining crop inventory (ending stocks), and average farm sale prices.  
   3. **Why text adds signal:** Production numbers alone do not explain sudden inventory drops. The text explains underlying causes, such as regional drought progression or foreign trade tariffs.  
7. Finance: Haiwen’s Multimodal Stock Dataset  
   1. **Text Content:** News articles on stock market   
   2. **TS:** Stock returns   
   3. **Why text adds signal:** Provides context on real-world events that may affect how the market behaves – this context can’t be recovered from TS   
8. Energy Markets and Power Grid Operations  
   1. **Text:**   
      1. *EIA Short-Term Energy Outlook (STEO):* Monthly analysis covering global oil, natural gas, and electricity market trends.  
      2. *Grid Operations Alerts:* Real-time market notices, Energy Emergency Alerts (EEA), CAISO Flex Alerts, and DOE OE-417 emergency outage descriptions (e.g., during major events like Winter Storm Uri).  
   2. **TS**: Monthly energy prices and stock levels (EIA), national hourly electricity demand (EIA-930), and real-time regional power demand, generation capacity, and wholesale electricity prices.  
   3. **Why text adds signal:** Real-time electricity prices can jump 100x during grid crises. Operational alerts describe physical generator failures, severe cold snaps, and emergency fuel orders that explain these massive price spikes. Alerts also include "busted" cases where emergency warnings were issued but outages were successfully avoided.  
9. Transportation: Aviation Operations and Flight Delays  
   1. **Text Content**: Real-time operational messages issued by the Air Traffic Control System Command Center (ATCSCC) explaining flight restrictions, ground stops, and airport delay expectations.  
   2. **TS**: Airport operational data recorded every 15 minutes, tracking flight arrival delays, taxiing wait times, and flight volume counts.  
   3. **Why text adds signal**: Flight delay statistics *how much* the planes will be late, but the text explains *why* — such as severe thunderstorm corridors or local runway closures.  
10. Healthcare  
    1. **Text Content:** Weekly narrative overviews from the FluView report detailing seasonal flu spread, regional severity levels, and virus strain characteristics.  
    2. **TS:** Weekly percentages of outpatient doctor visits for flu-like illness (ILINet data) and laboratory test positivity counts.  
    3. **Why text adds signal:** Infection numbers track outbreak size, but text supplies *qualitative biological context* (e.g., whether circulating virus strains match current seasonal vaccines).

