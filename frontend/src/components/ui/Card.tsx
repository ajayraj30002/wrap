import React from "react";

export function Card({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`card ${className}`}>
      {children}
    </div>
  );
}

export function CardHeader({ title, description, action }: { title: string; description?: string; action?: React.ReactNode }) {
  return (
    <div className="card-header flex justify-between items-start">
      <div>
        <h3 className="card-title">{title}</h3>
        {description && <p className="text-secondary text-sm mt-1">{description}</p>}
      </div>
      {action && <div>{action}</div>}
    </div> 
  ); 
}

export function CardBody({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={`card-body ${className}`}> 
      {children}  
    </div>
  );  
} 

export function MetricCard({ title, value, status }: { title: string; value: string | React.ReactNode; status?: "success" | "warning" | "error" }) {
  return (
    <div className="metric-card">
      <div className="metric-label">{title}</div>
      <div className={`metric-value ${status ? `text-${status}` : ''}`}>{value}</div>
    </div>
  );
}
