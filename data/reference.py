"""
Reference / master data used by the generator.

Using *real* IATA airport codes and US carrier names (rather than Faker noise)
makes the synthetic dataset credible to anyone who knows the domain, while the
volume + delay behaviour is fully simulated.
"""

# code, name, city, state, latitude, longitude, tz_offset, hub_weight
AIRPORTS = [
    ("ATL", "Hartsfield-Jackson Atlanta Intl", "Atlanta", "GA", 33.6407, -84.4277, -5, 10),
    ("DFW", "Dallas/Fort Worth Intl", "Dallas", "TX", 32.8998, -97.0403, -6, 9),
    ("DEN", "Denver Intl", "Denver", "CO", 39.8561, -104.6737, -7, 8),
    ("ORD", "Chicago O'Hare Intl", "Chicago", "IL", 41.9742, -87.9073, -6, 9),
    ("LAX", "Los Angeles Intl", "Los Angeles", "CA", 33.9416, -118.4085, -8, 9),
    ("JFK", "John F. Kennedy Intl", "New York", "NY", 40.6413, -73.7781, -5, 7),
    ("LGA", "LaGuardia", "New York", "NY", 40.7769, -73.8740, -5, 5),
    ("EWR", "Newark Liberty Intl", "Newark", "NJ", 40.6895, -74.1745, -5, 6),
    ("SFO", "San Francisco Intl", "San Francisco", "CA", 37.6213, -122.3790, -8, 7),
    ("SEA", "Seattle-Tacoma Intl", "Seattle", "WA", 47.4502, -122.3088, -8, 6),
    ("LAS", "Harry Reid Intl", "Las Vegas", "NV", 36.0840, -115.1537, -8, 6),
    ("MCO", "Orlando Intl", "Orlando", "FL", 28.4312, -81.3081, -5, 6),
    ("MIA", "Miami Intl", "Miami", "FL", 25.7959, -80.2870, -5, 6),
    ("CLT", "Charlotte Douglas Intl", "Charlotte", "NC", 35.2140, -80.9431, -5, 7),
    ("PHX", "Phoenix Sky Harbor Intl", "Phoenix", "AZ", 33.4342, -112.0116, -7, 6),
    ("IAH", "George Bush Intercontinental", "Houston", "TX", 29.9902, -95.3368, -6, 6),
    ("BOS", "Boston Logan Intl", "Boston", "MA", 42.3656, -71.0096, -5, 6),
    ("MSP", "Minneapolis-St Paul Intl", "Minneapolis", "MN", 44.8848, -93.2223, -6, 5),
    ("DTW", "Detroit Metro Wayne County", "Detroit", "MI", 42.2162, -83.3554, -5, 5),
    ("FLL", "Fort Lauderdale-Hollywood Intl", "Fort Lauderdale", "FL", 26.0742, -80.1506, -5, 5),
    ("PHL", "Philadelphia Intl", "Philadelphia", "PA", 39.8744, -75.2424, -5, 5),
    ("LGB", "Long Beach Airport", "Long Beach", "CA", 33.8177, -118.1516, -8, 3),
    ("BWI", "Baltimore/Washington Intl", "Baltimore", "MD", 39.1774, -76.6684, -5, 5),
    ("SLC", "Salt Lake City Intl", "Salt Lake City", "UT", 40.7899, -111.9791, -7, 5),
    ("DCA", "Ronald Reagan Washington National", "Washington", "DC", 38.8512, -77.0402, -5, 5),
    ("SAN", "San Diego Intl", "San Diego", "CA", 32.7338, -117.1933, -8, 5),
    ("TPA", "Tampa Intl", "Tampa", "FL", 27.9755, -82.5332, -5, 4),
    ("PDX", "Portland Intl", "Portland", "OR", 45.5898, -122.5951, -8, 4),
    ("STL", "St. Louis Lambert Intl", "St. Louis", "MO", 38.7487, -90.3700, -6, 4),
    ("HNL", "Daniel K. Inouye Intl", "Honolulu", "HI", 21.3187, -157.9225, -10, 4),
    ("AUS", "Austin-Bergstrom Intl", "Austin", "TX", 30.1975, -97.6664, -6, 4),
    ("NSH", "Nashville Intl", "Nashville", "TN", 36.1263, -86.6774, -6, 4),
    ("RDU", "Raleigh-Durham Intl", "Raleigh", "NC", 35.8801, -78.7880, -5, 4),
    ("MDW", "Chicago Midway Intl", "Chicago", "IL", 41.7868, -87.7522, -6, 4),
    ("DAL", "Dallas Love Field", "Dallas", "TX", 32.8471, -96.8518, -6, 4),
    ("OAK", "Oakland Intl", "Oakland", "CA", 37.7126, -122.2197, -8, 4),
    ("SMF", "Sacramento Intl", "Sacramento", "CA", 38.6954, -121.5908, -8, 3),
    ("MSY", "Louis Armstrong New Orleans Intl", "New Orleans", "LA", 29.9934, -90.2580, -6, 3),
    ("CLE", "Cleveland Hopkins Intl", "Cleveland", "OH", 41.4117, -81.8498, -5, 3),
    ("PIT", "Pittsburgh Intl", "Pittsburgh", "PA", 40.4915, -80.2329, -5, 3),
]

# code, name, is_low_cost, fleet_size, founded_year
CARRIERS = [
    ("AA", "American Airlines", False, 925, 1930),
    ("DL", "Delta Air Lines", False, 900, 1928),
    ("UA", "United Airlines", False, 850, 1926),
    ("WN", "Southwest Airlines", True, 800, 1967),
    ("AS", "Alaska Airlines", False, 330, 1932),
    ("B6", "JetBlue Airways", True, 280, 1998),
    ("NK", "Spirit Airlines", True, 200, 1980),
    ("F9", "Frontier Airlines", True, 130, 1994),
    ("HA", "Hawaiian Airlines", False, 60, 1929),
    ("G4", "Allegiant Air", True, 125, 1997),
]

# BTS-style cancellation reason codes
CANCELLATION_CODES = {
    "A": "Carrier",
    "B": "Weather",
    "C": "National Air System",
    "D": "Security",
}

WEATHER_CONDITIONS = ["Clear", "Cloudy", "Rain", "Fog", "Snow", "Thunderstorm"]
