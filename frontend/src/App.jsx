import { useState, useCallback } from 'react'
import AppNavbar from './components/AppNavbar'
import BikeMap from './components/BikeMap'
import StatusBar from './components/StatusBar'
import WeatherForecast from './components/WeatherForecast'
import AccountPage from './components/AccountPage'

export default function App() {
  const [weather, setWeather] = useState(null)
  const [stationCount, setStationCount] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [showForecast, setShowForecast] = useState(false)
  const [currentPage, setCurrentPage] = useState('map')
  const [user, setUser] = useState(null)
  const [rentalVersion, setRentalVersion] = useState(0)

  const handleRefresh = useCallback(() => {
    setWeather(null)
    setStationCount(null)
    setRefreshKey(k => k + 1)
  }, [])

  function handleLogin(token, name) {
    setUser({ token, name })
  }

  function handleLogout() {
    setUser(null)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh' }}>
      <AppNavbar
        currentPage={currentPage}
        onNavigate={setCurrentPage}
        user={user}
        onLogout={handleLogout}
      />

      {currentPage === 'map' && (
        <>
          <BikeMap
            refreshKey={refreshKey}
            onWeatherLoaded={setWeather}
            onStationsLoaded={count => setStationCount(count)}
            user={user}
            onRentalChange={() => setRentalVersion(v => v + 1)}
          />
          <StatusBar stationCount={stationCount} weather={weather} onRefresh={handleRefresh} onForecast={() => setShowForecast(true)} />
        </>
      )}

      {currentPage === 'account' && (
        <AccountPage user={user} onLogin={handleLogin} onLogout={handleLogout} rentalVersion={rentalVersion} />
      )}

      {showForecast && <WeatherForecast onClose={() => setShowForecast(false)} />}
    </div>
  )
}
