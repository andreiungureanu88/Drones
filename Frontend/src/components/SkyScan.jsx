import React, { useState, useEffect, useRef } from 'react';
import './../style/SkyScan.css';
import Loading from './Loading.jsx';
import FaceDetectionBand from './FaceDetectionBand.jsx'; 
import UnknownPersons from './UnknownPersons.jsx'; 

const SkyScan = () => {
  
  const [isRunning, setIsRunning] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [isButtonDisabled, setIsButtonDisabled] = useState(false);
  const [error, setError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(Date.now());
  const [streamActive, setStreamActive] = useState(false);
  
  const [rightDistance, setRightDistance] = useState(0);
  const [leftDistance, setLeftDistance] = useState(0);
  const [rightSweepAngle, setRightSweepAngle] = useState(0);
  const [leftSweepAngle, setLeftSweepAngle] = useState(0);
  
  const [detectedFaces, setDetectedFaces] = useState([]);
  const [faceHistory, setFaceHistory] = useState({});
  
  const imageRef = useRef(null);
  const statusTimerRef = useRef(null);
  const refreshTimerRef = useRef(null);
  const initialCheckTimerRef = useRef(null);
  const lastVideoLoadTimeRef = useRef(0);
  const buttonClickTimerRef = useRef(null);
  const facesPollingRef = useRef(null);
  
  const baseUrl = window.location.hostname === 'localhost' ? 'http://localhost:8000' : window.location.origin;
  const videoUrl = `${baseUrl}/skyscan/video?t=${refreshKey}`;
  
  // Funcție pentru a obține status și a actualiza distanțele
  const fetchDroneStatus = async () => {
    try {
      const response = await fetch(`${baseUrl}/skyscan/status`);
      const data = await response.json();
      
      console.log("Status response:", data);
      
      if (data.status === 'initializing') {
        setIsInitializing(true);
        setIsRunning(false);
        setIsButtonDisabled(false);
      } else if (data.status === 'running') {
        setIsInitializing(false);
        setIsRunning(true);
        setIsButtonDisabled(false);
        
        // Actualizăm valorile de distanță
        setRightDistance(data.metrics.right_distance);
        setLeftDistance(data.metrics.left_distance);
        setRightSweepAngle(data.metrics.right_sweep_angle);
        setLeftSweepAngle(data.metrics.left_sweep_angle);
      } else if (data.status === 'stopped' && (isRunning || isInitializing)) {
        setIsInitializing(false);
        setIsRunning(false);
        setStreamActive(false);
        setIsButtonDisabled(false);
        setError('Drona s-a oprit neașteptat');
      }
    } catch (err) {
      console.error('Eroare la obținerea stării dronei:', err);
    }
  };

  const fetchDetectedFaces = async () => {
    if (!isRunning || !streamActive) return;
    
    try {
      const response = await fetch(`${baseUrl}/skyscan/faces`);
      const data = await response.json();
      
      console.log("Date primite de la API faces:", data);
      
      if (data.status === 'success' && Array.isArray(data.faces)) {
      
        setDetectedFaces(data.faces);
        
        const newHistory = { ...faceHistory };

        data.faces.forEach(face => {
          if (face.is_known) {
            newHistory[face.id] = {
              ...face,
              lastSeen: face.lastSeen || new Date().getTime() 
            };
          }
        });
        
        setFaceHistory(newHistory);
        console.log("Face history actualizat:", newHistory);
      }
    } catch (err) {
      console.error('Eroare la obținerea fețelor detectate:', err);
    }
  };
  
  const resetFaceHistory = async () => {
    try {
      const response = await fetch(`${baseUrl}/skyscan/reset-faces`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      });
      
      const data = await response.json();
      
      if (data.status === 'success') {
        setFaceHistory({});
        console.log("Istoric fețe resetat cu succes");
      } else {
        console.error('Eroare la resetarea istoricului:', data.message);
      }
    } catch (err) {
      console.error('Eroare la resetarea istoricului:', err);
    }
  };


  useEffect(() => {
   
    if (isRunning && streamActive) {
      fetchDetectedFaces();
      
      facesPollingRef.current = setInterval(() => {
        fetchDetectedFaces();
      }, 5000);
    } else {
      
      if (facesPollingRef.current) {
        clearInterval(facesPollingRef.current);
        facesPollingRef.current = null;
      }
      
      if (!isRunning && detectedFaces.length > 0) {
        setDetectedFaces([]);
      }
    }
    
    return () => {
      if (facesPollingRef.current) {
        clearInterval(facesPollingRef.current);
      }
    };
  }, [isRunning, streamActive, baseUrl]);

  useEffect(() => {
    const statusPollInterval = streamActive ? 10000 : 1000; 
    
    if (isInitializing || (isRunning && !streamActive) || isRunning) {  // Adăugăm isRunning pentru a obține actualizări constante
      statusTimerRef.current = setInterval(() => {
        fetchDroneStatus();
      }, statusPollInterval);
      
      
      if (isRunning && !refreshTimerRef.current) {
        refreshTimerRef.current = setInterval(() => {
          const now = Date.now();
          const streamSeemsActive = (now - lastVideoLoadTimeRef.current) < 60000;
          
          if (!streamSeemsActive) {
            console.log("Stream inactiv detectat, reîmprospătare stream video");
            setRefreshKey(now);
          } else {
            console.log("Stream activ, nu este nevoie de reîmprospătare");
          }
        }, 30000); // Verificăm la fiecare 30 secunde
      }
    } else {
      if (statusTimerRef.current && (streamActive || (!isRunning && !isInitializing))) {
        clearInterval(statusTimerRef.current);
        statusTimerRef.current = null;
      }
    }

    return () => {
      if (statusTimerRef.current) clearInterval(statusTimerRef.current);
      if (refreshTimerRef.current) clearInterval(refreshTimerRef.current);
      if (initialCheckTimerRef.current) clearTimeout(initialCheckTimerRef.current);
      if (buttonClickTimerRef.current) clearTimeout(buttonClickTimerRef.current);
      if (facesPollingRef.current) clearInterval(facesPollingRef.current);
    };
  }, [isRunning, isInitializing, streamActive, baseUrl]);



  
  const handleStartScan = async () => {
    if (isButtonDisabled) return;
    
    setIsButtonDisabled(true);
    
    try {
      if (!isRunning && !isInitializing) {
        setIsLoading(true);
        setError(null);
        
        const response = await fetch(`${baseUrl}/skyscan/start`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        
        const data = await response.json();
        
        if (data.status === 'success') {
          setIsInitializing(true);
          setStreamActive(false);
          setRefreshKey(Date.now());
          setIsLoading(false); 
          
          if (initialCheckTimerRef.current) {
            clearTimeout(initialCheckTimerRef.current);
          }
          
          initialCheckTimerRef.current = setTimeout(() => {
            if (isInitializing && !isRunning) {
              console.log("Verificare inițială: drona încă se inițializează după timeout");
              reloadVideoStream();
            }
          }, 30000);
        } else {
          setError(data.message || 'Pornirea scanării a eșuat');
          setIsLoading(false);
          setIsButtonDisabled(false); // Deblocăm butonul în caz de eroare
        }
      } else {
        // Oprim drona
        setIsLoading(true);
        setError(null);
        
        // Important: Folosim cloneNode pentru a evita probleme cu appendChild 
        // dacă elementul există deja în DOM
        const existingOverlay = document.querySelector('.sky-landing-overlay');
        if (!existingOverlay) {
          const landingOverlay = document.createElement('div');
          landingOverlay.className = 'sky-landing-overlay';
          landingOverlay.innerHTML = `
            <div class="sky-loading-spinner"></div>
            <p>Drona aterizează...</p>
            <p>Vă rugăm așteptați</p>
          `;
          
          const videoContainer = document.querySelector('.sky-video-iframe-container');
          if (videoContainer) {
            videoContainer.appendChild(landingOverlay);
          }
        }
        
        const response = await fetch(`${baseUrl}/skyscan/stop`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' }
        });
        
        // Așteptăm puțin pentru a permite afișarea overlay-ului
        await new Promise(resolve => setTimeout(resolve, 5000));
        
        const data = await response.json();
        
        if (data.status === 'success' || data.status === 'not_running') {
          console.log("Drona a aterizat și a fost oprită cu succes");
        } else {
          setError(data.message || 'Oprirea scanării a eșuat');
        }
        
        // Curățăm overlay-ul
        const videoContainer = document.querySelector('.sky-video-iframe-container');
        const landingOverlay = document.querySelector('.sky-landing-overlay');
        if (videoContainer && landingOverlay) {
          videoContainer.removeChild(landingOverlay);
        }
        
        // Resetăm toate stările importante
        setIsRunning(false);
        setIsInitializing(false);
        setStreamActive(false);
        setIsLoading(false);
        
        // Resetăm valorile distanțelor
        setRightDistance(0);
        setLeftDistance(0);
        setRightSweepAngle(0);
        setLeftSweepAngle(0);
      }
    } catch (err) {
      console.error('Eroare la pornirea/oprirea scanării:', err);
      setError('Eroare de conexiune. Verificați dacă serverul rulează.');
      setIsRunning(false);
      setIsInitializing(false);
      setStreamActive(false);
      setIsLoading(false);
    } finally {
      setTimeout(() => {
        setIsButtonDisabled(false);
      }, 1000); 
    }
  };
  
  useEffect(() => {
    if (isRunning) {
      setIsButtonDisabled(false);
    }
  }, [isRunning]);
  

  const reloadVideoStream = () => {
    console.log("Reîncărcare manuală a stream-ului video");
    setRefreshKey(Date.now());
  };
  
  const handleVideoError = (error) => {
    console.error('Eroare la încărcarea stream-ului video:', error);
    setStreamActive(false);
    
    if (isRunning || isInitializing) {
      setTimeout(() => {
        reloadVideoStream();
      }, 1000);
    } else {
      setError('Nu s-a putut încărca fluxul video. Vă rugăm verificați conexiunea.');
    }
  };

  const handleVideoLoad = () => {
    console.log('Stream video încărcat cu succes');
    lastVideoLoadTimeRef.current = Date.now();
    setError(null);
    

    if (isInitializing) {
      setIsInitializing(false);
      setIsRunning(true);
    }
    
    setStreamActive(true);
    setIsButtonDisabled(false); 
    
    if (statusTimerRef.current) {
      clearInterval(statusTimerRef.current);
      statusTimerRef.current = null;
      
      statusTimerRef.current = setInterval(() => {
        fetchDroneStatus();
      }, 10000); 
    }
  };

  
  const getScanButtonText = () => {
    if (isLoading && !isRunning && !isInitializing) return 'Se procesează...';
    if (isInitializing && !isRunning) return 'Se aterizează...';
    if (isInitializing) return 'Se inițializează...';
    if (isRunning) return 'Oprește scanarea';
    return 'Începe scanarea';
  };

  const getScanButtonIcon = () => {
    if (isLoading && !isRunning && !isInitializing) return 'sync';
    if (isInitializing && !isRunning) return 'flight_land';
    if (isRunning) return 'stop_circle';
    return 'play_circle';
  };

  return (
    <div className="sky-scan-page">
      <div className="sky-scan-container">
        <div className="sky-video-section">
          <div className="sky-video-container">
            {isRunning || isInitializing ? (
              <div className="sky-video-iframe-container">
                <img 
                  ref={imageRef}
                  src={videoUrl} 
                  alt="Flux video scanare" 
                  className={`sky-video-stream ${isInitializing ? 'sky-video-reconnecting' : ''}`}
                  onLoad={handleVideoLoad}
                  onError={handleVideoError}
                />
                {isInitializing && (
                  <div className="sky-initializing-overlay">
                    <div className="sky-loading-spinner"></div>
                    <p>Se inițializează drona...</p>
                    <p>Vă rugăm să așteptați</p>
                  </div>
                )}
                {isRunning && (
                  <div className="sky-video-overlay">
                    <div className="sky-tracking-badge">
                      <span className="sky-tracking-dot"></span>
                      Detecție facială activă
                    </div>
                  </div>
                )}
                
                {/* Adăugăm afișarea distanțelor ca overlay pe video */}
                {isRunning && (rightDistance > 0 || leftDistance > 0) && (
                  <div className="sky-distances-overlay">
                    <div className="sky-distances-container">
                      <div className="sky-distance-item">
                        <span className="sky-distance-direction">← Stânga:</span>
                        <span className="sky-distance-value">{(leftDistance * 100).toFixed(0)} cm</span>
                        <span className="sky-angle-value">({leftSweepAngle.toFixed(1)}°)</span>
                      </div>
                      <div className="sky-distance-item">
                        <span className="sky-distance-direction">Dreapta →</span>
                        <span className="sky-distance-value">{(rightDistance * 100).toFixed(0)} cm</span>
                        <span className="sky-angle-value">({rightSweepAngle.toFixed(1)}°)</span>
                      </div>
                    </div>
                  </div>
                )}
                
              </div>
            ) : (
              <Loading message="Flux video în așteptare" />
            )}
          </div>

          {(isRunning || Object.keys(faceHistory).length > 0) && 
            <div className="sky-face-detection-wrapper">
              <FaceDetectionBand 
                faces={detectedFaces} 
                faceHistory={faceHistory} 
              />
              {Object.keys(faceHistory).length > 0 && (
                <button 
                  className="sky-reset-faces-btn" 
                  onClick={resetFaceHistory}
                  title="Șterge istoricul fețelor"
                >
                  <span className="material-symbols-rounded">delete</span>
                </button>
              )}
            </div>
          }
          
          {/* Adăugăm un panou separat pentru afișarea distanțelor sub video */}
          {isRunning && (rightDistance > 0 || leftDistance > 0) && (
            <div className="sky-distances-panel">
              <h3>Distanțe măsurate</h3>
              <div className="sky-distance-details">
                <div className="sky-distance-detail">
                  <div className="sky-detail-label">Stânga:</div>
                  <div className="sky-detail-value">{(leftDistance * 100).toFixed(0)} cm</div>
                </div>
                <div className="sky-distance-detail">
                  <div className="sky-detail-label">Dreapta:</div>
                  <div className="sky-detail-value">{(rightDistance * 100).toFixed(0)} cm</div>
                </div>
                <div className="sky-angle-details">
                  <div className="sky-detail-label">Unghi baleiaj stânga:</div>
                  <div className="sky-detail-value">{leftSweepAngle.toFixed(1)}°</div>
                </div>
                <div className="sky-angle-details">
                  <div className="sky-detail-label">Unghi baleiaj dreapta:</div>
                  <div className="sky-detail-value">{rightSweepAngle.toFixed(1)}°</div>
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="sky-right-section">
          <div className="sky-scan-control">
            <button 
              className={`sky-scan-btn 
                ${isRunning ? 'sky-scan-active' : ''} 
                ${isInitializing ? 'sky-scan-initializing' : ''} 
                ${isLoading && !isRunning && !isInitializing ? 'sky-scan-loading' : ''}`}
              onClick={handleStartScan}
              disabled={isButtonDisabled}
              style={{
                cursor: isButtonDisabled ? 'not-allowed' : 'pointer',
                opacity: isButtonDisabled && !isRunning && !isInitializing ? 0.7 : 1
              }}
            >
              <span className={`material-symbols-rounded ${(isLoading && !isRunning && !isInitializing) ? 'sky-spin-icon' : ''}`}>
                {getScanButtonIcon()}
              </span>
              <span className="sky-btn-text">
                {getScanButtonText()}
              </span>
            </button>
            
            {streamActive && (
              <div className="sky-stream-status sky-stream-active">
                <span className="sky-stream-indicator"></span>
                <span>Stream activ</span>
              </div>
            )}
            
            {error && (
              <div className="sky-scan-error">
                <span className="material-symbols-rounded">error</span>
                <span>{error}</span>
              </div>
            )}
          </div>

          <UnknownPersons 
            isLoading={isLoading}
            baseUrl={baseUrl}
            isRunning={isRunning} 
          />
        </div>
      </div>
    </div>
  );
};

export default SkyScan;