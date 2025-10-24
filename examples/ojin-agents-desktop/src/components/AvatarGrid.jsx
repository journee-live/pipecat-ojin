import React from 'react';
import AvatarCard from './AvatarCard';

function AvatarGrid({ config, onAvatarSelect }) {
  const { main_tags, avatars } = config;

  // Group avatars by tags
  const avatarsByTag = main_tags.map((tag) => ({
    tag,
    avatars: avatars.filter((avatar) => avatar.tags.includes(tag)),
  }));

  return (
    <div className="space-y-12">
      {avatarsByTag.map(({ tag, avatars: tagAvatars }) => (
        <div key={tag} className="space-y-4">
          <h2 className="text-xl font-semibold text-gray-800">{tag}</h2>
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-6">
            {tagAvatars.map((avatar) => (
              <AvatarCard key={avatar.id} avatar={avatar} onSelect={onAvatarSelect} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

export default AvatarGrid;
