import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import clsx from 'clsx';
import { useTheme } from '../contexts/ThemeContext';
import {
  LayoutDashboard,
  MessageSquare,
  BarChart3,
  Users,
  Calendar,
  Target,
  Sun,
  Moon,
  LogOut,
  Bot,
  ChevronLeft,
  ChevronRight,
  Menu
} from 'lucide-react';

interface SidebarProps {
  userEmail: string;
  onLogout: () => void;
}

interface NavItem {
  path: string;
  icon: React.ReactNode;
  label: string;
}

const navItems: NavItem[] = [
  { path: '/', icon: <LayoutDashboard size={20} />, label: 'Overview' },
  { path: '/conversations', icon: <MessageSquare size={20} />, label: 'Conversations' },
  { path: '/analytics', icon: <BarChart3 size={20} />, label: 'Analytics' },
  { path: '/consultants', icon: <Users size={20} />, label: 'Consultants' },
  { path: '/appointments', icon: <Calendar size={20} />, label: 'Appointments' },
  { path: '/programs', icon: <Target size={20} />, label: 'Programs' },
];

export const Sidebar: React.FC<SidebarProps> = ({ userEmail, onLogout }) => {
  const { theme, toggleTheme } = useTheme();
  const [isCollapsed, setIsCollapsed] = useState(false);
  
  const getInitial = (email: string) => email.charAt(0).toUpperCase();

  const getThemeTitle = () => {
    if (!isCollapsed) return undefined;
    return theme === 'dark' ? 'Light Mode' : 'Dark Mode';
  };

  return (
    <>
      {/* Mobile overlay */}
      {!isCollapsed && (
        <button 
          type="button"
          aria-label="Close sidebar"
          className="fixed inset-0 bg-black/50 z-40 lg:hidden transition-opacity cursor-default"
          onClick={() => setIsCollapsed(true)}
        />
      )}

      {/* Sidebar */}
      <aside 
        className={clsx(
          'fixed lg:static inset-y-0 left-0 z-50 flex flex-col bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 transition-all duration-300',
          isCollapsed ? '-translate-x-full lg:translate-x-0 lg:w-20' : 'translate-x-0 w-64'
        )}
      >
        {/* Logo */}
        <div className="flex items-center justify-between h-16 px-4 border-b border-gray-200 dark:border-gray-700">
          <div className={clsx('flex items-center gap-3', isCollapsed && 'lg:justify-center lg:w-full')}>
            <Bot size={28} className="text-primary-600" />
            {!isCollapsed && (
              <span className="font-bold text-gray-900 dark:text-white text-lg">Admin</span>
            )}
          </div>
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className="hidden lg:flex items-center justify-center w-8 h-8 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-500 dark:text-gray-400"
          >
            {isCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 p-3 space-y-1 overflow-y-auto">
          {navItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg font-medium transition-all',
                  isCollapsed && 'lg:justify-center',
                  isActive
                    ? 'bg-primary-50 dark:bg-primary-900/20 text-primary-600 dark:text-primary-400'
                    : 'text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white'
                )
              }
              title={isCollapsed ? item.label : undefined}
            >
              <span className="flex-shrink-0">{item.icon}</span>
              {!isCollapsed && <span>{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        {/* Theme Toggle & User Profile */}
        <div className="p-3 border-t border-gray-200 dark:border-gray-700 space-y-3">
          {/* Theme Toggle */}
          <button
            onClick={toggleTheme}
            className={clsx(
              'flex items-center gap-3 w-full px-3 py-2.5 rounded-lg font-medium text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 transition-all',
              isCollapsed && 'lg:justify-center'
            )}
            title={getThemeTitle()}
          >
            {theme === 'dark' ? <Sun size={20} /> : <Moon size={20} />}
            {!isCollapsed && <span>{theme === 'dark' ? 'Light Mode' : 'Dark Mode'}</span>}
          </button>

          {/* User Profile */}
          <div className={clsx(
            'flex items-center gap-3 p-3 rounded-lg bg-gray-50 dark:bg-gray-700/50',
            isCollapsed && 'lg:justify-center lg:p-2'
          )}>
            <div className="flex-shrink-0 flex h-10 w-10 items-center justify-center rounded-full bg-primary-600 text-white font-bold">
              {getInitial(userEmail)}
            </div>
            {!isCollapsed && (
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-900 dark:text-white truncate">{userEmail}</p>
                <p className="text-xs text-gray-500 dark:text-gray-400">Administrator</p>
              </div>
            )}
          </div>
          
          {/* Logout Button */}
          <button
            onClick={onLogout}
            className={clsx(
              'flex items-center gap-3 w-full px-3 py-2.5 rounded-lg font-medium text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-all',
              isCollapsed && 'lg:justify-center'
            )}
            title={isCollapsed ? 'Logout' : undefined}
          >
            <LogOut size={20} />
            {!isCollapsed && <span>Logout</span>}
          </button>
        </div>
      </aside>

      {/* Mobile toggle button */}
      <button
        onClick={() => setIsCollapsed(false)}
        className={clsx(
          'fixed bottom-4 left-4 z-30 lg:hidden flex items-center justify-center w-12 h-12 rounded-full bg-primary-600 text-white shadow-lg',
          !isCollapsed && 'hidden'
        )}
      >
        <Menu size={24} />
      </button>
    </>
  );
};

export default Sidebar;
