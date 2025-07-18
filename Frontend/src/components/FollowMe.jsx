import React, { useState, useRef, useEffect } from 'react';
import './../style/FollowMe.css';
import Loading from './Loading.jsx';

const FollowMe = () => {

  const [isStarted, setIsStarted] = useState(false);
  const [error, setError] = useState(null);
  const [refreshKey, setRefreshKey] = useState(Date.now());
  const [isLanding, setIsLanding] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  
  const [isPhotoSaved, setIsPhotoSaved] = useState(false);
  
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const [recordingInterval, setRecordingInterval] = useState(null);
  
  const [batteryLevel, setBatteryLevel] = useState(null);
  const [isFetchingBattery, setIsFetchingBattery] = useState(false);
  
  const imageRef = useRef(null);
  const canvasRef = useRef(null);
  const batteryPollingRef = useRef(null);
  const lastBatteryUpdateRef = useRef(0);
  const batteryPollingTimeoutRef = useRef(null);
  const startedRef = useRef(false); 
  
  const baseUrl = window.location.hostname === 'localhost' ? 'http://localhost:8000' : `${window.location.protocol}//${window.location.hostname}:8000`;

  useEffect(() => {
    startedRef.current = isStarted;
  }, [isStarted]);

  useEffect(() => {
    return () => {
      if (recordingInterval) {
        clearInterval(recordingInterval);
      }
      
      stopBatteryPolling();
      
      if (batteryPollingTimeoutRef.current) {
        clearTimeout(batteryPollingTimeoutRef.current);
      }
      
      if (isRecording) {
        try {
          fetch(`${baseUrl}/followme/recording/stop`, { method: 'POST' })
            .catch(err => console.error('Eroare la oprirea inregistrarii:', err));
        } catch (err) {
          console.error('Eroare la oprirea inregistrarii la demontare:', err);
        }
      }
    };
  }, [recordingInterval, isRecording, baseUrl]);

  /**
   * Functie pentru obtinerea nivelului bateriei
   * @param {boolean} forceUpdate - Forteaza actualizarea chiar daca a fost recent verificata
   * @param {boolean} logResponse - Daca sa se afiseze raspunsul în consola
   */
  const fetchBatteryLevel = async (forceUpdate = false, logResponse = false) => {
    if (!startedRef.current) {
      if (logResponse) {
        console.log("[DEBUG] Cerere baterie ignorata - drona nu este activa");
      }
      return;
    }
    
    const now = Date.now();
    if (!forceUpdate && (now - lastBatteryUpdateRef.current) < 4500) {
      return; 
    }
    
    try {
      if (isFetchingBattery && !forceUpdate) return;
      
      setIsFetchingBattery(true);
      lastBatteryUpdateRef.current = now;
      
      if (logResponse) {
        console.log("[DEBUG] Trimitere cerere GET pentru baterie la", new Date().toTimeString());
      }
      
      const response = await fetch(`${baseUrl}/followme/stats`);
      if (response.ok) {
        const data = await response.json();
        
        if (logResponse) {
          console.log("[DEBUG] Raspuns baterie:", data);
        }
        
        if (data.success && data.stats && data.stats.battery !== undefined) {
          const batteryValue = typeof data.stats.battery === 'string' 
            ? parseInt(data.stats.battery, 10) 
            : data.stats.battery;
          
          if (batteryValue !== batteryLevel) {
            setBatteryLevel(batteryValue);
            if (logResponse) {
              console.log("[DEBUG] Nivel baterie actualizat:", batteryValue);
            }
          }
        }
      }
    } catch (err) {
      console.error("Eroare la obținerea starii bateriei:", err);
    } finally {
      setIsFetchingBattery(false);
    }
  };


  const startBatteryPolling = () => {
    if (!startedRef.current) {
      console.log("[DEBUG] Nu se porneste polling baterie - drona nu este activa");
      return;
    }
    
    stopBatteryPolling();
    
    fetchBatteryLevel(true, true);
    
   
    console.log("[DEBUG] Pornire polling baterie");
    batteryPollingRef.current = setInterval(() => {
      
      if (!startedRef.current) {
        console.log("[DEBUG] Oprire automata polling baterie - drona nu mai este activa");
        stopBatteryPolling();
        return;
      }
      fetchBatteryLevel(false, false);
    }, 5000);
  };

  const stopBatteryPolling = () => {
    if (batteryPollingRef.current) {
      console.log("[DEBUG] Oprire polling baterie");
      clearInterval(batteryPollingRef.current);
      batteryPollingRef.current = null;
    }
  };


  const ensureBatteryPollingActive = () => {
    if (!startedRef.current) {
      console.log("[DEBUG] Nu se verifica bateria - drona nu este activa");
      return;
    }
    
    fetchBatteryLevel(true, true);
    
    if (!batteryPollingRef.current && startedRef.current) {
      console.log("[DEBUG] Repornire polling baterie");
      
      setTimeout(() => {
        if (startedRef.current) {
          startBatteryPolling();
        }
      }, 100);
    }
  };

  useEffect(() => {
    if (isStarted) {
      const startPollingDelay = setTimeout(() => {
        if (startedRef.current) {
          console.log("[DEBUG] Drona activa - pornire polling baterie");
          startBatteryPolling();
        }
      }, 1000);
      
      return () => {
        clearTimeout(startPollingDelay);
      };
    } else {
      console.log("[DEBUG] Drona inactiva - oprire polling baterie");
      stopBatteryPolling();
      setBatteryLevel(null);
    }
  }, [isStarted]);

  useEffect(() => {
    if (isStarted && !isRecording) {
     
      const checkPollingAfterRecording = () => {
        if (!startedRef.current) return; 
        if (batteryPollingRef.current) return; 
        
        console.log("[DEBUG] Verificare polling baterie dupa inregistrare");
        ensureBatteryPollingActive();
      };
      
      batteryPollingTimeoutRef.current = setTimeout(checkPollingAfterRecording, 3000);
    }
    
    return () => {
      if (batteryPollingTimeoutRef.current) {
        clearTimeout(batteryPollingTimeoutRef.current);
      }
    };
  }, [isRecording, isStarted]);

  const startDrone = async () => {
    try {
      setError(null);
      setIsInitializing(true);
      
      stopBatteryPolling();
      setBatteryLevel(null);
      
      const takeoffResponse = await fetch(
        `${baseUrl}/followme/start`,
        { method: 'POST' }
      );
      
      if (takeoffResponse.ok) {
        const takeoffResult = await takeoffResponse.json();
        
        if (takeoffResult.success) {
          setIsStarted(true);
          setRefreshKey(Date.now());
          
        } else {
          setError(`Nu s-a putut decola drona: ${takeoffResult.message}`);
        }
      } else {
        setError('Eroare la decolare. Verificati conexiunea cu serverul.');
      }
    } catch (err) {
      console.error('Eroare la pornirea dronei:', err);
      setError(`Eroare la pornirea dronei: ${err.message}`);
    } finally {
      setIsInitializing(false);
    }
  };


  const takePhoto = () => {
    if (!isStarted) {
      setError("Nu există un stream video activ pentru a face o fotografie");
      return;
    }
  
    try {
      setIsPhotoSaved(false);
      setError(null);
      
      const timestamp = Date.now();
      const now = new Date();
      const fileName = `drone_photo_${now.getFullYear()}${(now.getMonth()+1).toString().padStart(2, '0')}${
        now.getDate().toString().padStart(2, '0')}_${
        now.getHours().toString().padStart(2, '0')}${
        now.getMinutes().toString().padStart(2, '0')}${
        now.getSeconds().toString().padStart(2, '0')}.jpg`;
      
      fetch(`${baseUrl}/followme/frame?t=${timestamp}`)
        .then(response => {
          if (!response.ok) {
            throw new Error(`Server error: ${response.status}`);
          }
          return response.blob();
        })
        .then(blob => {
          const blobUrl = URL.createObjectURL(blob);
          
          const downloadLink = document.createElement('a');
          downloadLink.href = blobUrl;
          downloadLink.download = fileName;
          downloadLink.style.display = 'none';
          
          document.body.appendChild(downloadLink);
          downloadLink.click();
          
          setTimeout(() => {
            document.body.removeChild(downloadLink);
            URL.revokeObjectURL(blobUrl);
            
            setIsPhotoSaved(true);
            
            setTimeout(() => {
              setIsPhotoSaved(false);
            }, 1500);
            
            if (startedRef.current) {
              ensureBatteryPollingActive();
            }
          }, 100);
        })
        .catch(err => {
          console.error("Eroare la descarcarea fotografiei:", err);
          setError(`Nu s-a putut descarca fotografia: ${err.message}`);
          setIsPhotoSaved(false);
        });
      
    } catch (err) {
      console.error("Eroare la capturarea fotografiei:", err);
      setError(`Nu s-a putut captura fotografia: ${err.message}`);
      setIsPhotoSaved(false);
    }
  };


  const formatRecordingTime = (seconds) => {
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes.toString().padStart(2, '0')}:${remainingSeconds.toString().padStart(2, '0')}`;
  };

  const toggleRecording = async () => {
    try {
      setError(null);
      
      if (isRecording) {
        const stopResponse = await fetch(
          `${baseUrl}/followme/recording/stop`,
          { method: 'POST' }
        );
        
        if (stopResponse.ok) {
          const result = await stopResponse.json();
          
          if (result.success) {
            console.log('[DEBUG] Inregistrare salvata:', result.filename);
            
            if (recordingInterval) {
              clearInterval(recordingInterval);
              setRecordingInterval(null);
            }
            
            setRecordingTime(0);
            setIsRecording(false);

            if (startedRef.current) {
              await fetchBatteryLevel(true, true);
            }
            
            if (result.filename) {
              const timestamp = Date.now();
              const downloadUrl = `${baseUrl}/followme/recording/download/${result.filename}?t=${timestamp}`;
              
              const link = document.createElement('a');
              link.href = downloadUrl;
              link.download = result.filename;
              link.target = '_blank';
              link.style.display = 'none';
              
              document.body.appendChild(link);
              link.click();
              
              setTimeout(() => {
                document.body.removeChild(link);
                
                if (startedRef.current) {
                  setTimeout(() => {
                    console.log("[DEBUG] Verificare baterie dupa descarcare");
                    ensureBatteryPollingActive();
                  }, 1000);
                }
              }, 100);
              
              if (startedRef.current) {
                const ensurePollingIntervals = [2000, 5000, 10000];
                ensurePollingIntervals.forEach(delay => {
                  setTimeout(() => {
                    if (startedRef.current) {
                      ensureBatteryPollingActive();
                    }
                  }, delay);
                });
              }
            }
            
            if (startedRef.current && !batteryPollingRef.current) {
              startBatteryPolling();
            }
          } else {
            setError(`Nu s-a putut opri inregistrarea: ${result.message}`);
          }
        } else {
          setError('Eroare la oprirea inregistrarii. Verificați conexiunea cu serverul.');
        }
      } else {
        const startResponse = await fetch(
          `${baseUrl}/followme/recording/start`,
          { method: 'POST' }
        );
        
        if (startResponse.ok) {
          const result = await startResponse.json();
          
          if (result.success) {
            console.log('[DEBUG] Inregistrare pornita');
            
            setIsRecording(true);
            
            const interval = setInterval(() => {
              setRecordingTime(prev => prev + 1);
            }, 1000);
            
            setRecordingInterval(interval);
            
            if (startedRef.current) {
              ensureBatteryPollingActive();
            }
          } else {
            setError(`Nu s-a putut porni inregistrarea: ${result.message}`);
          }
        } else {
          setError('Eroare la pornirea inregistrarii. Verificați conexiunea cu serverul.');
        }
      }
    } catch (err) {
      console.error('Eroare la procesarea inregistrarii:', err);
      setError(`Eroare la procesarea inregistrarii: ${err.message}`);
    }
  };


  const landDrone = async () => {
    try {
      setError(null);
      setIsLanding(true);

      if (isRecording) {
        try {
          await fetch(`${baseUrl}/followme/recording/stop`, { method: 'POST' });
          
          if (recordingInterval) {
            clearInterval(recordingInterval);
            setRecordingInterval(null);
          }
          
          setIsRecording(false);
          setRecordingTime(0);
        } catch (err) {
          console.error('Eroare la oprirea inregistrarii la aterizare:', err);
        }
      }
      
      stopBatteryPolling();
      
      const landResponse = await fetch(
        `${baseUrl}/followme/land`,
        { method: 'POST' }
      );
      
      if (landResponse.ok) {
        const landResult = await landResponse.json();
        setIsStarted(false);
        setRefreshKey(Date.now());
        setBatteryLevel(null);
      } else {
        setError('Eroare la aterizare. Verificati conexiunea cu serverul.');
      }
    } catch (err) {
      console.error('Eroare la aterizarea dronei:', err);
      setError(`Eroare la aterizarea dronei: ${err.message}`);
    } finally {
      setIsLanding(false);
    }
  };


  const handleImageError = () => {
    console.error('Eroare la încarcarea stream-ului video');
    setRefreshKey(Date.now());
  };
 
  const videoUrl = `${baseUrl}/followme/video?t=${refreshKey}`;

  return (
    <div className="follow-me-page">
      <div className="follow-me-container">
        <canvas ref={canvasRef} style={{ display: 'none' }}></canvas>
        <div className="video-section">
          <div className="video-container">
            {isStarted ? (
              <img 
                ref={imageRef}
                src={videoUrl}
                alt="Stream video dronă" 
                className="video-stream"
                onError={handleImageError}
                crossOrigin="anonymous"
              />
            ) : (
              <Loading 
                message={isInitializing ? "Inițializare dronă..." : "În așteptarea conectării..."} 
              />
            )}
            
            {isStarted && (
              <div className="video-overlay">
                <div className="tracking-badge">
                  <span className="tracking-dot"></span>
                  Urmărire activă
                </div>
                
                {isRecording && (
                  <div className="recording-badge">
                    <span className="recording-indicator"></span>
                    {formatRecordingTime(recordingTime)}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        
        {/* Zona de control */}
        <div className="control-section">
          <h2 className="section-title">Control Dronă</h2>
          
          <div className="control-description">
            <p>Folosiți aceste butoane pentru a controla drona și funcționalitățile de urmărire.</p>
          </div>
          
          <div className="controls-grid">
            {/* Buton START */}
            <button 
              className={`control-btn start-btn ${isStarted ? 'disabled' : ''}`}
              onClick={startDrone}
              disabled={isStarted || isLanding || isInitializing}
            >
              <span className={`material-symbols-rounded ${isInitializing ? 'loading' : ''}`}>
                {isInitializing ? 'autorenew' : 'flight_takeoff'}
              </span>
              <span className="btn-text">
                {isInitializing ? 'Inițializare...' : 'Start'}
              </span>
            </button>
            
            {/* Buton Photo */}
            <button 
              className="control-btn photo-btn"
              onClick={takePhoto}
              disabled={!isStarted || isLanding || isInitializing || isPhotoSaved}
            >
              <span className={`material-symbols-rounded ${isPhotoSaved ? 'success-anim' : ''}`}>
                {isPhotoSaved ? 'check_circle' : 'photo_camera'}
              </span>
              <span className="btn-text">
                {isPhotoSaved ? 'Salvat!' : 'Photo'}
              </span>
            </button>
            
            {/* Buton Inregistrare */}
            <button 
              className={`control-btn record-btn ${isRecording ? 'recording' : ''}`}
              onClick={toggleRecording}
              disabled={!isStarted || isLanding || isInitializing}
            >
              <span className={`material-symbols-rounded ${isRecording ? 'pulse-recording' : ''}`}>
                {isRecording ? 'radio_button_checked' : 'videocam'}
              </span>
              <span className="btn-text">
                {isRecording 
                  ? `Înregistrare ${formatRecordingTime(recordingTime)}` 
                  : 'Înregistrare'}
              </span>
            </button>
            
            {/* Buton Aterizare */}
            <button 
              className="control-btn land-btn"
              onClick={landDrone}
              disabled={!isStarted || isLanding || isInitializing}
            >
              <span className={`material-symbols-rounded ${isLanding ? 'loading' : ''}`}>
                {isLanding ? 'autorenew' : 'flight_land'}
              </span>
              <span className="btn-text">{isLanding ? 'Aterizare...' : 'Aterizare'}</span>
            </button>
          </div>
          
          {error && <div className="error-message">{error}</div>}
          
          <div className="status-section">
            <div className="status-indicator">
              <div className={`status-dot ${isStarted ? 'active' : 'inactive'}`}></div>
              <span className="status-text">
                {isInitializing ? 'Inițializare dronă...' : 
                 isStarted ? 'Dronă activă' : 'Dronă inactivă'}
              </span>
            </div>
          </div>
          
          {/* Zona de afisare a bateriei */}
          <div className="status-section battery-section">
            {isStarted ? (
              batteryLevel !== null ? (
                <div className="battery-indicator">
                  <span className="material-symbols-rounded battery-icon">
                    {batteryLevel >= 80 ? 'battery_full' : 
                     batteryLevel >= 50 ? 'battery_5_bar' : 
                     batteryLevel >= 20 ? 'battery_3_bar' : 'battery_alert'}
                  </span>
                  <div className="battery-bar-container">
                    <div 
                      className={`battery-bar ${
                        batteryLevel >= 50 ? 'good' : 
                        batteryLevel >= 20 ? 'warning' : 'critical'
                      }`} 
                      style={{ width: `${batteryLevel}%` }}
                    ></div>
                  </div>
                  <span className="battery-text">{batteryLevel}%</span>
                </div>
              ) : (
                <div className="battery-indicator">
                  <span className="material-symbols-rounded battery-icon loading-icon">sync</span>
                  <span className="battery-text status-text">Se obține nivelul bateriei...</span>
                </div>
              )
            ) : (
              <div className="battery-indicator">
                <span className="material-symbols-rounded battery-icon disabled-icon">battery_unknown</span>
                <span className="battery-text status-text">Informații indisponibile</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default FollowMe;