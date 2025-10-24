import React, { useState, useEffect } from 'react';
import AvatarCard from './AvatarCard';

function AvatarGrid({ config, onAvatarSelect }) {
  const { main_tags, avatars } = config;
  const [cardSize, setCardSize] = useState('medium');

  // Group avatars by tags
  const avatarsByTag = main_tags.map((tag) => ({
    tag,
    avatars: avatars.filter((avatar) => avatar.tags.includes(tag)),
  }));

  // Determine card size based on viewport width
  useEffect(() => {
    const updateCardSize = () => {
      const width = window.innerWidth;
      
      if (width >= 1600) {
        setCardSize('large');
      } else if (width >= 1200) {
        setCardSize('medium');
      } else {
        setCardSize('small');
      }
    };

    updateCardSize();
    window.addEventListener('resize', updateCardSize);
    return () => window.removeEventListener('resize', updateCardSize);
  }, []);

  return (
    <div className="flex flex-wrap justify-between gap-1">
      {avatarsByTag.map(({ tag, avatars: tagAvatars }) => (
        <div key={tag} className="flex-1 min-w-0" style={{ minWidth: '200px' }}>
          <h2 className="text-lg font-semibold text-gray-900 mb-3 text-center">{tag}</h2>
          <div className="flex flex-wrap gap-3 justify-center">
            {tagAvatars.map((avatar) => (
              <AvatarCard 
                key={avatar.id} 
                avatar={avatar} 
                onSelect={onAvatarSelect}
                size={cardSize}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default AvatarGrid;
