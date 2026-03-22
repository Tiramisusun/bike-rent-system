import { useState, useCallback } from 'react'
import Navbar from './components/Navbar'
import BikeMap from './components/BikeMap'
import StatusBar from './components/StatusBar'

export default function App() {
  const [weather, setWeather] = useState(null)
  const [stationCount, setStationCount] = useState(null)
  // Incrementing this key triggers a data refresh in BikeMap
  const [refreshKey, setRefreshKey] = useState(0)

  const handleRefresh = useCallback(() => {
    setWeather(null)
    setStationCount(null)
    setRefreshKey(k => k + 1)
  }, [])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <Navbar weather={weather} onRefresh={handleRefresh} />
      <BikeMap
        refreshKey={refreshKey}
        onWeatherLoaded={setWeather}
        onStationsLoaded={count => setStationCount(count)}
      />
      <StatusBar stationCount={stationCount} />
    </div>
  )
}
