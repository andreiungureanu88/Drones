import React, { useState, useEffect, useRef } from 'react';
import './../style/UnknownPersons.css';

const UnknownPersons = ({ 
  isLoading: externalIsLoading,
  baseUrl,
  isRunning 
}) => {
 
  const [nameInput, setNameInput] = useState('');
  const [unknownFaces, setUnknownFaces] = useState([]);
  const [isAddingPerson, setIsAddingPerson] = useState(false);
  const [selectedFace, setSelectedFace] = useState(null);
  const [addPersonError, setAddPersonError] = useState(null);
  const [isLoadingFaces, setIsLoadingFaces] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  
  const pollingRef = useRef(null);

  const fetchUnknownFaces = async () => {
    if (!isRunning) return;
    
    try {
      setIsLoadingFaces(true);
      const response = await fetch(`${baseUrl}/skyscan/unknown-faces`);
      const data = await response.json();
      
      if (data.status === 'success' && Array.isArray(data.faces)) {
        setUnknownFaces(data.faces);
      }
    } catch (err) {
      console.error('Eroare la obținerea fețelor necunoscute:', err);
    } finally {
      setIsLoadingFaces(false);
    }
  };

  useEffect(() => {
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
    
    if (isRunning) {
      console.log("Pornire polling fețe necunoscute");
      
      fetchUnknownFaces();
      
      pollingRef.current = setInterval(() => {
        fetchUnknownFaces();
      }, 5000); 
    } else {
      console.log("Oprire polling fețe necunoscute - drona este oprită");

    }

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [isRunning, baseUrl]); 


  const handleNameChange = (e) => {
    setNameInput(e.target.value);
  };


  const handleSelectUnknownFace = (face) => {
    setSelectedFace(face);
    setNameInput(''); 
    setIsAddingPerson(true);
    setAddPersonError(null);
  };
  
  const handleCancelAddPerson = () => {
    setIsAddingPerson(false);
    setSelectedFace(null);
    setNameInput('');
  };
  
  const handleDeleteUnknownFace = async (faceId) => {
    try {
      setIsProcessing(true);
      const response = await fetch(`${baseUrl}/skyscan/unknown-faces/${faceId}`, {
        method: 'DELETE'
      });
      
      const data = await response.json();
      
      if (data.status === 'success') {
        setUnknownFaces(prev => prev.filter(face => face.id !== faceId));
      } else {
        console.error('Eroare la ștergerea feței:', data.message);
      }
    } catch (err) {
      console.error('Eroare la ștergerea feței:', err);
    } finally {
      setIsProcessing(false);
    }
  };
  
  const handleAddUnknownPerson = async () => {
    if (!nameInput.trim() || !selectedFace) {
      setAddPersonError('Numele trebuie completat.');
      return;
    }
    
    try {
      setIsProcessing(true);
      setAddPersonError(null);
      
      const response = await fetch(`${baseUrl}/skyscan/add-person`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          face_id: selectedFace.id,
          name: nameInput
        })
      });
      
      const data = await response.json();
      
      if (data.status === 'success') {
        setUnknownFaces(prev => prev.filter(face => face.id !== selectedFace.id));
        setIsAddingPerson(false);
        setSelectedFace(null);
        setNameInput('');
        alert(`Persoana "${nameInput}" a fost adăugată în baza de date.`);
      } else {
        setAddPersonError(data.message || 'Eroare la adăugarea persoanei.');
      }
    } catch (err) {
      console.error('Eroare la adăugarea persoanei:', err);
      setAddPersonError('Eroare de comunicare cu serverul.');
    } finally {
      setIsProcessing(false);
    }
  };

  const isAnyLoading = externalIsLoading || isProcessing;

  return (
    <div className="sky-persons-section">
      <h2 className="sky-section-title">Persoane necunoscute</h2>
      
      <div className="sky-persons-description">
        <p>Identifică persoanele detectate și adaugă-le în baza de date.</p>
      </div>
      
      {isAddingPerson && selectedFace ? (
        <div className="sky-unknown-face-add">
          <h3 className="sky-unknown-face-title">Adaugă persoană nouă</h3>
          
          <div className="sky-unknown-face-content">
            <div className="sky-unknown-face-image">
              <img 
                src={`data:image/jpeg;base64,${selectedFace.image}`} 
                alt="Față necunoscută"
              />
            </div>
            
            <div className="sky-unknown-face-form">
              <input 
                type="text"
                placeholder="Numele persoanei"
                value={nameInput}
                onChange={handleNameChange}
                className="sky-person-name-input"
              />
              
              {addPersonError && (
                <div className="sky-add-person-error">{addPersonError}</div>
              )}
              
              <div className="sky-unknown-face-buttons">
                <button 
                  className="sky-control-btn sky-cancel-btn"
                  onClick={handleCancelAddPerson}
                  disabled={isAnyLoading}
                >
                  <span className="material-symbols-rounded">close</span>
                  <span className="sky-btn-text">Anulează</span>
                </button>
                
                <button 
                  className="sky-control-btn sky-add-person-btn"
                  onClick={handleAddUnknownPerson}
                  disabled={!nameInput.trim() || isAnyLoading}
                >
                  <span className={`material-symbols-rounded ${isProcessing ? 'sky-spin-icon' : ''}`}>
                    {isProcessing ? 'sync' : 'person_add'}
                  </span>
                  <span className="sky-btn-text">
                    {isProcessing ? 'Se adaugă...' : 'Adaugă persoană'}
                  </span>
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <>
          {unknownFaces.length > 0 ? (
            <div className="sky-unknown-faces-list">
              <h3 className="sky-unknown-faces-title">Fețe necunoscute detectate</h3>
              
              <div className="sky-unknown-faces-grid">
                {unknownFaces.map((face) => (
                  <div className="sky-unknown-face-item" key={face.id}>
                    <div className="sky-unknown-face-image">
                      <img 
                        src={`data:image/jpeg;base64,${face.image}`} 
                        alt="Față necunoscută"
                      />
                    </div>
                    
                    <div className="sky-unknown-face-actions">
                      <button 
                        className="sky-control-btn sky-add-btn"
                        onClick={() => handleSelectUnknownFace(face)}
                        disabled={isAnyLoading}
                      >
                        <span className="material-symbols-rounded">person_add</span>
                      </button>
                      
                      <button 
                        className="sky-control-btn sky-delete-btn"
                        onClick={() => handleDeleteUnknownFace(face.id)}
                        disabled={isAnyLoading}
                      >
                        <span className="material-symbols-rounded">delete</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="sky-unknown-faces-empty">
              {isLoadingFaces ? (
                <p>Se încarcă fețele necunoscute...</p>
              ) : (
                <p>{isRunning ? 
                  "Nu există fețe necunoscute detectate." : 
                  "Pornește scanarea pentru a detecta fețe necunoscute."}
                </p>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default UnknownPersons;