import React from "react";

export function TableContainer({ children, className = "" }: { children?: React.ReactNode; className?: string }) {
  return (
    <div className={`table-container ${className}`}>
      {children}
    </div>
  );
}

export function Table({ children, className = "" }: { children?: React.ReactNode; className?: string }) {
  return <table className={`table ${className}`}>{children}</table>;
}

export function TableHead({ children }: { children?: React.ReactNode }) {
  return <thead>{children}</thead>;
}

export function TableBody({ children }: { children?: React.ReactNode }) {
  return <tbody>{children}</tbody>;
}

export function TableRow({ children, className = "" }: { children?: React.ReactNode; className?: string }) {
  return <tr className={className}>{children}</tr>;
}

export function TableHeader({ children, className = "" }: { children?: React.ReactNode; className?: string }) {
  return <th className={className}>{children}</th>;
}

export function TableCell({ children, className = "", ...props }: React.TdHTMLAttributes<HTMLTableCellElement>) {
  return <td className={className} {...props}>{children}</td>;
}

export function EmptyState({ icon, title, description, action }: { icon?: React.ReactNode, title: string, description?: string, action?: React.ReactNode }) {
  return (
    <div className="empty-state">
      {icon && <div className="empty-icon">{icon}</div>}
      <h3 className="empty-title">{title}</h3>
      {description && <p className="empty-desc">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
