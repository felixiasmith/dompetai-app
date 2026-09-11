import React from 'react';
import { usePrivacy } from './PrivacyContext';
import { Eye, EyeOff } from 'lucide-react'; // Menggunakan Lucide Icons sesuai spesifikasi Tech Stack

export const WalletCard: React.FC = () => {
  // Panggil fungsi sensor dari global context
  const { isPrivacyMode, togglePrivacyMode, maskAmount, maskText } = usePrivacy();

  // Data sampel dari profil demo Tech Professional
  const sampleWallet = { name: 'BCA (Utama)', balance: 18500000 };

  return (
    <div className="bg-[#151b2c] border border-slate-800 p-5 rounded-2xl shadow-md max-w-sm">
      <div className="flex justify-between items-center mb-3">
        <span className="text-xs text-slate-400 font-medium uppercase tracking-wider">
          {maskText(sampleWallet.name)}
        </span>
        
        {/* Tombol Toggle Mata untuk Hidup/Matikan Sensor */}
        <button 
          onClick={togglePrivacyMode}
          className="text-slate-400 hover:text-slate-200 p-1.5 rounded-lg bg-slate-900/50 hover:bg-slate-900 transition border border-slate-800"
          title={isPrivacyMode ? "Buka Sensor" : "Aktifkan Mode Privasi"}
        >
          {isPrivacyMode ? <EyeOff size={14} /> : <Eye size={14} />}
        </button>
      </div>

      <div>
        <p className="text-xs text-slate-500 font-normal">Total Saldo Terbaca</p>
        {/* Angka otomatis disamarkan jika mode privasi bernilai true */}
        <p className={`text-2xl font-bold mt-1 transition-all ${isPrivacyMode ? 'text-blue-400 select-none' : 'text-emerald-400'}`}>
          {maskAmount(sampleWallet.balance)}
        </p>
      </div>
    </div>
  );
};
