import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

interface Property {
  id: string;
  name: string;
  timezone: string;
}

const MONTHS = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December'
];

// Seed reservations are all in March 2024, so default the period there.
const DEFAULT_MONTH = 3;
const DEFAULT_YEAR = 2024;
const FIRST_YEAR = 2023;
const YEARS = Array.from(
  { length: new Date().getFullYear() - FIRST_YEAR + 1 },
  (_, i) => FIRST_YEAR + i
);

const Dashboard: React.FC = () => {
  const [properties, setProperties] = useState<Property[]>([]);
  const [propertiesLoading, setPropertiesLoading] = useState(true);
  const [propertiesError, setPropertiesError] = useState('');
  const [selectedProperty, setSelectedProperty] = useState('');
  // 0 = all time
  const [month, setMonth] = useState(DEFAULT_MONTH);
  const [year, setYear] = useState(DEFAULT_YEAR);

  useEffect(() => {
    let cancelled = false;

    const fetchProperties = async () => {
      try {
        // Only the logged-in tenant's properties come back from the API
        const response = await SecureAPI.getDashboardProperties();
        if (cancelled) return;
        const list: Property[] = response?.data ?? [];
        setProperties(list);
        setSelectedProperty(list[0]?.id ?? '');
      } catch (err) {
        if (cancelled) return;
        setPropertiesError('Failed to load properties');
        console.error(err);
      } finally {
        if (!cancelled) setPropertiesLoading(false);
      }
    };

    fetchProperties();
    return () => {
      cancelled = true;
    };
  }, []);

  const selectClass =
    "block w-full sm:w-auto px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm";

  return (
    <div className="p-4 lg:p-6 min-h-full">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-6 text-gray-900">Property Management Dashboard</h1>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 lg:p-6">
          <div className="mb-6">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4">
              <div>
                <h2 className="text-lg lg:text-xl font-medium text-gray-900 mb-2">Revenue Overview</h2>
                <p className="text-sm lg:text-base text-gray-600">
                  Monthly performance insights for your properties
                </p>
              </div>

              <div className="flex flex-col sm:flex-row gap-3">
                {/* Property Selector */}
                <div className="flex flex-col sm:items-end">
                  <label className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                  <select
                    value={selectedProperty}
                    onChange={(e) => setSelectedProperty(e.target.value)}
                    disabled={propertiesLoading || properties.length === 0}
                    className={`${selectClass} min-w-[200px]`}
                  >
                    {properties.map((property) => (
                      <option key={property.id} value={property.id}>
                        {property.name}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Period Selector (month/year in each property's local timezone) */}
                <div className="flex flex-col sm:items-end">
                  <label className="text-xs font-medium text-gray-700 mb-1">Month</label>
                  <select
                    value={month}
                    onChange={(e) => setMonth(Number(e.target.value))}
                    className={selectClass}
                  >
                    <option value={0}>All time</option>
                    {MONTHS.map((name, i) => (
                      <option key={name} value={i + 1}>
                        {name}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="flex flex-col sm:items-end">
                  <label className="text-xs font-medium text-gray-700 mb-1">Year</label>
                  <select
                    value={year}
                    onChange={(e) => setYear(Number(e.target.value))}
                    disabled={month === 0}
                    className={selectClass}
                  >
                    {YEARS.map((y) => (
                      <option key={y} value={y}>
                        {y}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {propertiesLoading && <div className="text-sm text-gray-500">Loading properties...</div>}
            {propertiesError && <div className="p-4 text-red-500 bg-red-50 rounded-lg">{propertiesError}</div>}
            {!propertiesLoading && !propertiesError && properties.length === 0 && (
              <div className="text-sm text-gray-500">No properties found for your account.</div>
            )}
            {selectedProperty && (
              <RevenueSummary
                propertyId={selectedProperty}
                month={month || undefined}
                year={month ? year : undefined}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
