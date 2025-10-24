import React from 'react';

function AvatarCard({ avatar, onSelect }) {
  const handleClick = () => {
    console.log('Avatar selected:', avatar.name, 'Persona ID:', avatar.ojin_persona_id, 'Hume Config:', avatar.hume_config_id);
    onSelect(avatar);
  };

  return (
    <div
      onClick={handleClick}
      className="group cursor-pointer bg-white rounded-2xl overflow-hidden shadow-sm hover:shadow-lg transition-all duration-200 transform hover:scale-105"
    >
      <div className="aspect-square relative bg-gradient-to-br from-gray-100 to-gray-200">
        {avatar.image ? (
          <img
            src={avatar.image}
            alt={avatar.name}
            className="w-full h-full object-cover"
            onError={(e) => {
              e.target.style.display = 'none';
            }}
          />
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
      
      <div className="p-3">
        <h3 className="text-sm font-semibold text-gray-900 truncate">{avatar.name}</h3>
        {avatar.description && (
          <p className="text-xs text-gray-500 truncate mt-1">{avatar.description}</p>
        )}
      </div>
    </div>
  );
}

export default AvatarCard;
