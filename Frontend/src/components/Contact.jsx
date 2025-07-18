import React from 'react';

const Contact = () => {
  return (
    <div className="min-h-screen bg-zinc-900 text-zinc-50 p-4">
      <div className="max-w-2xl mx-auto">
        {/* Header Section */}
        <div className="text-center mb-12">
          <h1 className="text-4xl font-bold mb-4 bg-gradient-to-r from-zinc-50 to-zinc-300 bg-clip-text text-transparent">
            Contactează-ne
          </h1>
          <p className="text-zinc-400 text-lg">
            Suntem aici pentru a te ajuta. Găsește informațiile de contact de mai jos.
          </p>
        </div>

        <div className="space-y-6">
          {/* Contact Information */}
          <div className="bg-zinc-800/50 backdrop-blur-sm rounded-2xl p-6 border border-zinc-700/50">
            <h2 className="text-2xl font-semibold mb-6 text-zinc-50">Informații de contact</h2>
            
            <div className="space-y-4">
              <div className="flex items-center space-x-4">
                <div className="w-12 h-12 bg-zinc-700/50 rounded-xl flex items-center justify-center">
                  <svg className="w-6 h-6 text-zinc-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 4.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                </div>
                <div>
                  <h3 className="font-medium text-zinc-50">Email</h3>
                  <p className="text-zinc-400">andreiungureanu161@gmail.com</p>
                </div>
              </div>

              <div className="flex items-center space-x-4">
                <div className="w-12 h-12 bg-zinc-700/50 rounded-xl flex items-center justify-center">
                  <svg className="w-6 h-6 text-zinc-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" />
                  </svg>
                </div>
                <div>
                  <h3 className="font-medium text-zinc-50">Telefon</h3>
                  <p className="text-zinc-400">+40 787 824 781</p>
                </div>
              </div>

              <div className="flex items-center space-x-4">
                <div className="w-12 h-12 bg-zinc-700/50 rounded-xl flex items-center justify-center">
                  <svg className="w-6 h-6 text-zinc-300" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </div>
                <div>
                  <h3 className="font-medium text-zinc-50">Adresă</h3>
                  <p className="text-zinc-400">Str. Speranței Nr. 321<br />București, România</p>
                </div>
              </div>
            </div>
          </div>

          {/* Hours */}
          <div className="bg-zinc-800/50 backdrop-blur-sm rounded-2xl p-6 border border-zinc-700/50">
            <h3 className="text-xl font-semibold mb-4 text-zinc-50">Program de lucru</h3>
            <div className="space-y-2 text-zinc-400">
              <div className="flex justify-between">
                <span>Luni - Vineri</span>
                <span>09:00 - 18:00</span>
              </div>
              <div className="flex justify-between">
                <span>Sâmbătă</span>
                <span>10:00 - 16:00</span>
              </div>
              <div className="flex justify-between">
                <span>Duminică</span>
                <span>Închis</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Contact;