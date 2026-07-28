import { useEffect, useState } from 'react';

let showToastFn: ((msg: string) => void) | null = null;

export function toast(msg: string) {
  if (showToastFn) showToastFn(msg);
}

export default function Toast() {
  const [message, setMessage] = useState('');
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    showToastFn = (msg: string) => {
      setMessage(msg);
      setVisible(true);
      setTimeout(() => setVisible(false), 1800);
    };
    return () => { showToastFn = null; };
  }, []);

  return (
    <div className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-[200] px-5 py-3 bg-gray-900 text-white rounded-xl shadow-2xl text-sm font-medium transition-all duration-300 ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4 pointer-events-none'}`}>
      {message}
    </div>
  );
}
