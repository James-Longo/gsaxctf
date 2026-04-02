import React, { useState, useEffect } from 'react';

export default function Footage() {
  const [albums, setAlbums] = useState([]);

  useEffect(() => {
    fetch('/albums.json')
      .then(res => res.json())
      .then(data => {
        const sorted = data.sort((a, b) => a.title.localeCompare(b.title));
        setAlbums(sorted);
      })
      .catch(err => console.error("Could not load albums.json", err));
  }, []);

  return (
    <div className="footage-container">
      <div className="footage-header">
        <h2>Team Footage</h2>
      </div>

      <div className="album-grid">
        {albums.map(album => (
          <a
            key={album.id}
            href={album.url}
            target="_blank"
            rel="noopener noreferrer"
            className="album-card"
          >
            <div className="album-card-banner" style={{ padding: 0, position: 'relative' }}>
              {album.coverImage ? (
                <img 
                  src={album.coverImage} 
                  alt={album.title} 
                  referrerPolicy="no-referrer" 
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }} 
                />
              ) : (
                <svg 
                  className="google-photos-icon" 
                  viewBox="0 0 24 24" 
                  width="48" 
                  height="48"
                >
                  <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8zm-2-5.5l6-4.5-6-4.5v9z" fill="currentColor"/>
                </svg>
              )}
            </div>
            <div className="album-card-content">
              <h3>{album.title}</h3>
              <div className="album-action">
                <span className="action-text">Open in Google Photos</span>
                <svg className="action-arrow" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M5 12h14M12 5l7 7-7 7"/>
                </svg>
              </div>
            </div>
          </a>
        ))}
      </div>
    </div>
  );
}
