import React from "react";

export function FormGroup({ children, className = "" }: { children: React.ReactNode, className?: string }) {
  return <div className={`form-group ${className}`}>{children}</div>;
}

export function Label({ children, htmlFor, className = "" }: { children: React.ReactNode, htmlFor?: string, className?: string }) {
  return <label htmlFor={htmlFor} className={`form-label ${className}`}>{children}</label>;
}

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className = "", ...props }, ref) => {
    return (
      <input ref={ref} className={`form-input ${className}`} {...props} />
    );
  }
);
Input.displayName = "Input";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className = "", children, ...props }, ref) => {
    return (
      <select ref={ref} className={`form-select ${className}`} {...props}>
        {children}
      </select>
    );
  }
);
Select.displayName = "Select";

