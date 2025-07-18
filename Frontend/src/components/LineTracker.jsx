import React, { useState, useEffect, useRef } from 'react';
import "./../style/LineTracker.css";

const API_BASE_URL = "http://localhost:8000";

const LineTracker = () => {
  const [isStarted, setIsStarted] = useState(false);
  const [isAutonomous, setIsAutonomous] = useState(false);
  const [sensorValues, setSensorValues] = useState([0, 0, 0]);
  const [telemetry, setTelemetry] = useState({
    rotation: 0,
    speed: 0,
    battery: null
  });
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(Date.now());
  
  const statsPollingRef = useRef(null);
  const startedRef = useRef(false);
  const abortControllerRef = useRef(null);
  const errorCount = useRef(0);
  
  useEffect(() => {
    startedRef.current = isStarted;
  }, [isStarted]);
  
  useEffect(() => {
    return () => {
      if (statsPollingRef.current) {
        clearInterval(statsPollingRef.current);
      }
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);
  
  const resetAppState = () => {
    console.log("Resetare completă a stării aplicației");
    setIsStarted(false);
    setIsAutonomous(false);
    setIsLoading(false);
    setRefreshKey(Date.now());
    setSensorValues([0, 0, 0]);
    setTelemetry({
      rotation: 0,
      speed: 0,
      battery: null
    });
    
    if (statsPollingRef.current) {
      clearInterval(statsPollingRef.current);
      statsPollingRef.current = null;
    }
  };
  
  const fetchDroneStats = async () => {
    if (!startedRef.current) return;
    
    try {
      const response = await fetch(`${API_BASE_URL}/linefollower/stats`);
      if (response.ok) {
        const data = await response.json();
        
        if (data.success && data.stats) {
          if (data.stats.active === false && isStarted) {
            console.log("Detected drone has landed from stats - resetting state");
            resetAppState();
            return;
          }
          
          setSensorValues(data.stats.sensor_readings || [0, 0, 0]);
          setIsAutonomous(data.stats.autonomous || false);
          
          setTelemetry({
            rotation: data.stats.rotation || 0,
            speed: data.stats.speed || 0,
            battery: data.stats.battery
          });
          
          errorCount.current = 0;
        }
      } else {
        console.warn("Server returned non-OK response for stats:", response.status);
        
        if (isStarted) {
          errorCount.current++;
          if (errorCount.current > 3) {
            console.warn("Multiple failed attempts to fetch stats - resetting app state");
            resetAppState();
            errorCount.current = 0;
          }
        }
      }
    } catch (err) {
      console.error("Eroare la obținerea statisticilor dronei:", err);
      
      if (isStarted) {
        errorCount.current++;
        if (errorCount.current > 3) {
          console.warn("Multiple connection errors - resetting app state");
          resetAppState();
          errorCount.current = 0;
        }
      }
    }
  };
  
  useEffect(() => {
    if (isStarted) {
      fetchDroneStats();
      
      if (statsPollingRef.current) {
        clearInterval(statsPollingRef.current);
      }
      
      statsPollingRef.current = setInterval(fetchDroneStats, 1000);
    } else {
      if (statsPollingRef.current) {
        clearInterval(statsPollingRef.current);
        statsPollingRef.current = null;
      }
    }
    
    return () => {
      if (statsPollingRef.current) {
        clearInterval(statsPollingRef.current);
      }
    };
  }, [isStarted]);
  
  const startDrone = async () => {
    try {
      setError(null);
      setIsLoading(true);
      
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();
      
      const response = await fetch(`${API_BASE_URL}/linefollower/start`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        signal: abortControllerRef.current.signal
      });
      
      const data = await response.json();
      
      if (data.success) {
        setIsStarted(true);
        setRefreshKey(Date.now());
      } else {
        setError(`Nu s-a putut porni drona: ${data.message}`);
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error('Eroare la pornirea dronei:', err);
        setError(`Eroare de conexiune. Asigurați-vă că serverul rulează la ${API_BASE_URL}`);
      }
    } finally {
      setIsLoading(false);
    }
  };
  
  const switchToAutonomous = async () => {
    try {
      setError(null);
      setIsLoading(true);
      
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();
      
      const response = await fetch(`${API_BASE_URL}/linefollower/autonomous`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        signal: abortControllerRef.current.signal
      });
      
      const data = await response.json();
      
      if (data.success) {
        setIsAutonomous(true);
      } else {
        setError(`Nu s-a putut comuta la modul autonom: ${data.message}`);
      }
    } catch (err) {
      if (err.name !== 'AbortError') {
        console.error('Eroare la comutarea modului:', err);
        setError('Eroare de conexiune. Încercați din nou.');
      }
    } finally {
      setIsLoading(false);
    }
  };
  
  const landDrone = async () => {
    try {
      setError(null);
      setIsLoading(true);
      
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      abortControllerRef.current = new AbortController();
      
      const timeoutId = setTimeout(() => {
        console.log("Timeout pentru cererea de aterizare - reset forțat");
        resetAppState();
      }, 10000); 
      
      try {
        const response = await fetch(`${API_BASE_URL}/linefollower/land`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json'
          },
          signal: abortControllerRef.current.signal
        });
        
        clearTimeout(timeoutId);
        
        resetAppState();
        
        const data = await response.json();
        if (!data.success) {
          console.warn(`Avertisment la aterizare: ${data.message}`);
        }
      } catch (fetchErr) {
        clearTimeout(timeoutId);
        
        resetAppState();
        
        if (fetchErr.name !== 'AbortError') {
          console.error('Eroare la aterizarea dronei:', fetchErr);
          setError('Eroare de conexiune. Drona a fost probabil aterizată, dar verificați starea acesteia.');
        }
      }
    } catch (err) {
      console.error('Eroare generală la aterizare:', err);
      resetAppState();
    } finally {
      setIsLoading(false);
    }
  };
  
  const refreshVideoStream = () => {
    setRefreshKey(Date.now());
  };
  
  const getStreamUrl = (endpoint) => {
    return `${API_BASE_URL}${endpoint}?t=${refreshKey}`;
  };
  
  return (
    <div className="page-content line-tracker-page">
      <div className="line-tracker-container">
        {error && (
          <div className="error-banner">
            <p className="error-message">{error}</p>
            <button className="error-close" onClick={() => setError(null)}>×</button>
          </div>
        )}
        
        <div className="drone-interface">
          <div className="status-bar">
            <div className="connection-status">
              <div className={`status-indicator ${isStarted ? 'connected' : 'connecting'}`} />
              <span>{isStarted ? 'Dronă conectată' : 'Dronă inactivă'}</span>
            </div>
            
            <div className="mode-indicator">
              <span className="mode-label">Mod:</span>
              <span>{!isStarted ? 'Standby' : isAutonomous ? 'Autonom' : 'Manual'}</span>
            </div>
            
            {telemetry.battery !== null && (
              <div className="battery-indicator">
                <span className="battery-icon">🔋</span>
                <span className="battery-text">{telemetry.battery}%</span>
              </div>
            )}
          </div>
          
          {/* Noul layout simplificat cu camera si senzori pe aceeasi linie */}
          <div className="simplified-layout">
            <div className="camera-container">
              <h3 className="feed-title">Vizualizare Dronă</h3>
              {isStarted ? (
                <div className="camera-feed-wrapper">
                  <img 
                    src={getStreamUrl('/linefollower/camera')} 
                    alt="Stream video dronă" 
                    className="main-feed"
                    onError={refreshVideoStream}
                    key={`camera-${refreshKey}`}
                  />
                  {/* Overlay pentru a indica punctul central și sensitivity */}
                  <div className="camera-overlay">
                    <div className="center-point"></div>
                    <div className="sensitivity-indicator"></div>
                  </div>
                </div>
              ) : (
                <div className="feed-placeholder">
                  <div className="feed-overlay">Streaming video indisponibil</div>
                </div>
              )}
            </div>
            
            <div className="sensors-container">
              <h3 className="sensors-title">Senzori virtuali</h3>
              <div className="sensors-horizontal-row">
                {Array(3).fill(0).map((_, index) => (
                  <div key={`sensor-container-${index}-${refreshKey}`} className="sensor-item">
                    <p className="sensor-title">Senzor {index + 1}</p>
                    {isStarted ? (
                      <img 
                        src={getStreamUrl(`/linefollower/sensor/${index}`)} 
                        alt={`Vizualizare senzor ${index + 1}`} 
                        className="sensor-feed"
                        onError={refreshVideoStream}
                        key={`sensor-${index}-${refreshKey}`}
                      />
                    ) : (
                      <div className="sensor-feed-placeholder">
                        <div className="sensor-overlay">Senzor inactiv</div>
                      </div>
                    )}
                    <div className={`sensor-value ${isStarted && sensorValues[index] === 1 ? 'active-sensor' : ''}`}>
                      {isStarted ? (sensorValues[index] === 1 ? 'Activ' : 'Inactiv') : 'Inactiv'}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
          
          <div className="control-panel">
            <div className="control-buttons-row">
              {!isStarted ? (
                <button 
                  onClick={startDrone} 
                  className="control-btn start-btn"
                  disabled={isLoading}
                >
                  {isLoading ? 'Pornire...' : 'Start dronă'}
                </button>
              ) : !isAutonomous ? (
                <button 
                  onClick={switchToAutonomous} 
                  className="control-btn auto-btn"
                  disabled={isLoading}
                >
                  {isLoading ? 'Se comută...' : 'Mod autonom'}
                </button>
              ) : (
                <button 
                  onClick={landDrone} 
                  className="control-btn land-btn"
                  disabled={isLoading}
                >
                  {isLoading ? 'Aterizare...' : 'Aterizare'}
                </button>
              )}
            </div>
          </div>
          
          {isAutonomous && (
            <div className="telemetry-panel">
              <h3 className="telemetry-title">Telemetrie zbor</h3>
              <div className="telemetry-grid">
                <div className="telemetry-item">
                  <span className="telemetry-label">Rotație</span>
                  <span className="telemetry-value">{telemetry.rotation}</span>
                </div>
                <div className="telemetry-item">
                  <span className="telemetry-label">Viteză</span>
                  <span className="telemetry-value">{telemetry.speed}</span>
                </div>
              </div>
            </div>
          )}
          
          <div className="instructions-panel">
            <h3 className="instructions-title">Instrucțiuni de control</h3>
            {!isStarted ? (
              <p className="instruction-text">
                Apăsați butonul "Start dronă" pentru a decola drona și a începe controlul manual.
              </p>
            ) : !isAutonomous ? (
              <div className="instruction-text">
                <p>Controlul manual este activ în fereastra serverului.</p>
                <ul className="key-instructions">
                  <li><span className="key-highlight">W/S</span> - înainte/înapoi</li>
                  <li><span className="key-highlight">A/D</span> - stânga/dreapta</li>
                  <li><span className="key-highlight">Up/Down</span> - sus/jos</li>
                  <li><span className="key-highlight">Enter</span> - pornește modul autonom</li>
                  <li><span className="key-highlight">L</span> - aterizează drona</li>
                </ul>
                <p>
                  Apăsați butonul "Mod autonom" sau tasta <span className="key-highlight">Enter</span> 
                  în fereastra serverului pentru a începe urmărirea liniei în mod autonom.
                </p>
              </div>
            ) : (
              <div className="instruction-text">
                <p>Modul de urmărire autonomă a liniei este activ.</p>
                <p>
                  Drona urmărește acum automat linia. Apăsați butonul "Aterizare" 
                  sau tasta <span className="key-highlight">L</span> în fereastra serverului pentru a ateriza drona.
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default LineTracker;