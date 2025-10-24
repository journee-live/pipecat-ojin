import React, { useState } from 'react';

function AvatarCard({ avatar, onSelect, size = 'medium' }) {
  const [imageLoaded, setImageLoaded] = useState(false);
  const [imageError, setImageError] = useState(false);

  const handleClick = () => {
    console.log('Avatar selected:', avatar.name, 'Persona ID:', avatar.ojin_persona_id, 'Hume Config:', avatar.hume_config_id);
    onSelect(avatar);
  };

  // Show description only for medium and large cards
  const showDescription = size !== 'small';
  
  // Fixed widths for each size
  const widths = {
    small: 180,
    medium: 240,
    large: 300
  };
  
  const width = widths[size] || widths.medium;
  
  // Netflix-style sizing
  const paddingClass = size === 'large' ? 'p-4' : size === 'medium' ? 'p-3' : 'p-2';
  const nameClass = size === 'large' ? 'text-base' : size === 'medium' ? 'text-sm' : 'text-xs';
  const descClass = size === 'large' ? 'text-sm' : 'text-xs';

  return (
    <div
      onClick={handleClick}
      className="group cursor-pointer bg-white rounded-lg overflow-hidden shadow-md hover:shadow-xl transition-all duration-300 transform hover:scale-105 hover:z-10"
      style={{ width: `${width}px`, flexShrink: 0 }}
    >
      <div className="aspect-square relative bg-gradient-to-br from-gray-100 to-gray-200">
        {avatar.image && !imageError ? (
          <>
            {!imageLoaded && (
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-8 h-8 border-4 border-gray-300 border-t-blue-500 rounded-full animate-spin"></div>
              </div>
            )}
            <img
              src={avatar.image}
              alt={avatar.name}
              className={`w-full h-full object-cover transition-opacity duration-300 ${
                imageLoaded ? 'opacity-100' : 'opacity-0'
              }`}
              onLoad={() => setImageLoaded(true)}
              onError={() => {
                console.error('Failed to load image:', avatar.image);
                setImageError(true);
              }}
            />
          </>
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <div className="w-16 h-16 rounded-full bg-gray-300 flex items-center justify-center">
              <span className="text-2xl text-gray-600 font-semibold">
                {avatar.name.charAt(0).toUpperCase()}
              </span>
            </div>
          </div>
        )}
        
        {/* Overlay with name on hover */}
        <div className="absolute inset-0 bg-black bg-opacity-0 group-hover:bg-opacity-10 transition-all duration-200" />
      </div>
      
      <div className={paddingClass}>
        <h3 className={`${nameClass} font-semibold text-gray-900 truncate`}>{avatar.name}</h3>
        {showDescription && avatar.description && (
          <p className={`${descClass} text-gray-500 truncate mt-1`}>{avatar.description}</p>
        )}
      </div>
    </div>
  );
}

export default AvatarCard;
