import React, { ReactNode, useEffect } from 'react';
import { Button } from './Button';

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  type?: 'info' | 'success' | 'error' | 'warning';
  actions?: ReactNode;
  size?: 'sm' | 'md' | 'lg' | 'xl';
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  type = 'info',
  actions,
  size = 'md',
}) => {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = 'unset';
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [isOpen]);

  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
    }
    return () => document.removeEventListener('keydown', handleEscape);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const iconMap = {
    info: '💡',
    success: '✅',
    error: '❌',
    warning: '⚠️',
  };

  const sizeClasses = {
    sm: 'max-w-sm',
    md: 'max-w-md',
    lg: 'max-w-lg',
    xl: 'max-w-2xl',
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in">
      {/* Backdrop */}
      <button
        type="button"
        aria-label="Close modal"
        className="absolute inset-0 bg-black/50 dark:bg-black/70 cursor-default"
        onClick={onClose}
      />
      
      {/* Modal */}
      <div className={`relative z-10 w-full ${sizeClasses[size]} rounded-xl bg-white dark:bg-gray-800 shadow-2xl animate-scale-in max-h-[90vh] flex flex-col`}>
        {/* Header */}
        <div className="flex items-center justify-between p-5 border-b border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <span className="text-2xl">{iconMap[type]}</span>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h2>
          </div>
          <button
            onClick={onClose}
            className="flex items-center justify-center w-8 h-8 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
          >
            <span className="text-xl">×</span>
          </button>
        </div>
        
        {/* Content */}
        <div className="flex-1 overflow-y-auto p-5 text-gray-700 dark:text-gray-300">
          {children}
        </div>
        
        {/* Footer */}
        {actions && (
          <div className="flex justify-end gap-3 p-5 border-t border-gray-200 dark:border-gray-700">
            {actions}
          </div>
        )}
        {!actions && (
          <div className="flex justify-end gap-3 p-5 border-t border-gray-200 dark:border-gray-700">
            <Button onClick={onClose} variant="secondary">
              Close
            </Button>
          </div>
        )}
      </div>
    </div>
  );
};

export default Modal;
