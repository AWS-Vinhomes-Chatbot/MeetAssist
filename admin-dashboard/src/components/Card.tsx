import React, { ReactNode } from 'react';
import clsx from 'clsx';

interface StatCardProps {
  title: string;
  value: string | number;
  icon: string;
  change?: string;
  changeType?: 'positive' | 'negative' | 'neutral';
  color?: 'blue' | 'green' | 'orange' | 'purple';
}

export const StatCard: React.FC<StatCardProps> = ({
  title,
  value,
  icon,
  change,
  changeType = 'neutral',
  color = 'blue',
}) => {
  const colorClasses = {
    blue: 'bg-blue-50 dark:bg-blue-900/20 border-blue-200 dark:border-blue-800',
    green: 'bg-green-50 dark:bg-green-900/20 border-green-200 dark:border-green-800',
    orange: 'bg-orange-50 dark:bg-orange-900/20 border-orange-200 dark:border-orange-800',
    purple: 'bg-purple-50 dark:bg-purple-900/20 border-purple-200 dark:border-purple-800',
  };

  const iconBgClasses = {
    blue: 'bg-blue-100 dark:bg-blue-800/50',
    green: 'bg-green-100 dark:bg-green-800/50',
    orange: 'bg-orange-100 dark:bg-orange-800/50',
    purple: 'bg-purple-100 dark:bg-purple-800/50',
  };

  const changeClasses = {
    positive: 'text-green-600 dark:text-green-400',
    negative: 'text-red-600 dark:text-red-400',
    neutral: 'text-gray-500 dark:text-gray-400',
  };

  return (
    <div className={clsx('rounded-xl border p-5 transition-all hover:shadow-md', colorClasses[color])}>
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-600 dark:text-gray-400">{title}</p>
          <p className="mt-2 text-2xl sm:text-3xl font-bold text-gray-900 dark:text-white truncate">{value}</p>
          {change && (
            <p className={clsx('mt-2 text-sm font-medium', changeClasses[changeType])}>
              {change}
            </p>
          )}
        </div>
        <div className={clsx('flex-shrink-0 p-3 rounded-lg', iconBgClasses[color])}>
          <span className="text-2xl">{icon}</span>
        </div>
      </div>
    </div>
  );
};

interface CardProps {
  title?: string;
  children: ReactNode;
  className?: string;
  actions?: ReactNode;
  noPadding?: boolean;
}

export const Card: React.FC<CardProps> = ({ title, children, className, actions, noPadding }) => {
  return (
    <div className={clsx(
      'rounded-xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 shadow-sm transition-all',
      !noPadding && 'p-5 sm:p-6',
      className
    )}>
      {(title || actions) && (
        <div className={clsx(
          'flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4',
          noPadding && 'px-5 sm:px-6 pt-5 sm:pt-6'
        )}>
          {title && <h3 className="text-lg font-semibold text-gray-900 dark:text-white">{title}</h3>}
          {actions && <div className="flex gap-2 flex-shrink-0">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  );
};

export default Card;
