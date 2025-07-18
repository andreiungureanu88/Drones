import React, { useState, useEffect } from 'react';
import './../style/FaceDetectionBand.css';

const FaceDetectionBand = ({ faces, faceHistory }) => {
  const [newFaces, setNewFaces] = useState({});
  
  const historyEntries = Object.values(faceHistory || {});
  
  const sortedFaces = historyEntries.sort((a, b) => a.name.localeCompare(b.name));
  
  useEffect(() => {
    const currentFaceIds = Object.keys(faceHistory);
    const newFacesObj = {};
    
    currentFaceIds.forEach(id => {
      if (!newFaces[id]) {
        newFacesObj[id] = true;
        
        setTimeout(() => {
          setNewFaces(prev => {
            const updated = {...prev};
            delete updated[id];
            return updated;
          });
        }, 2000);
      }
    });
    
    if (Object.keys(newFacesObj).length > 0) {
      setNewFaces(prev => ({...prev, ...newFacesObj}));
    }
  }, [faceHistory]);
  
  const activeFacesCount = faces.filter(f => f.is_known && f.active).length;
  
  return (
    <div className="sky-face-detection-band">
      <div className="sky-face-band-header">
        <div className="sky-face-band-title">
          Persoane recunoscute
        </div>
        {activeFacesCount > 0 && (
          <div className="sky-face-count-badge">
            {activeFacesCount} active
          </div>
        )}
      </div>
      
      <div className="sky-face-band-inner">
        {sortedFaces.length > 0 ? (
          <div className="sky-face-list">
            {sortedFaces.map((face) => {
              
              const isCurrentlyDetected = faces.some(f => f.id === face.id && f.is_known && f.active);
              const isNewFace = newFaces[face.id];
              
              return (
                <div 
                  key={face.id} 
                  className={`sky-face-item ${isCurrentlyDetected ? 'sky-face-active' : 'sky-face-inactive'} ${isNewFace ? 'sky-face-new' : ''}`}
                >
                  <span className="sky-face-name">
                    {face.name}
                  </span>
                  <span className="sky-face-confidence">
                    {isCurrentlyDetected 
                      ? `${(face.confidence * 100).toFixed(0)}%` 
                      : 'Detectat anterior'}
                  </span>
                </div>
              );
            })}
          </div>
        ) : (
          <div className="sky-face-placeholder">
            Nicio persoană cunoscută detectată
          </div>
        )}
      </div>
    </div>
  );
};

export default FaceDetectionBand;