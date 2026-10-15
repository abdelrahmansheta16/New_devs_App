import React, { useEffect, useState } from 'react';
import { SecureAPI } from '../lib/secureApi';

const MONTH_NAMES = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
];

interface RevenueData {
    property_id: string;
    // Exact decimal string already rounded half-up to cents by the API (e.g. "2250.00").
    // Never round it again with float math in the browser.
    total_revenue: string;
    currency: string;
    reservations_count: number;
    month?: number | null;
    year?: number | null;
}

interface RevenueSummaryProps {
    propertyId: string;
    month?: number;
    year?: number;
    showRaw?: boolean;
}

const formatMoney = (amount: string, currency: string) => {
    try {
        return new Intl.NumberFormat(undefined, { style: 'currency', currency }).format(Number(amount));
    } catch {
        // Unknown currency code: fall back to the plain amount
        return `${currency} ${amount}`;
    }
};

export const RevenueSummary: React.FC<RevenueSummaryProps> = ({ propertyId, month, year, showRaw }) => {
    const [data, setData] = useState<RevenueData | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        // Ignore responses from a previous property/period so a slow request can't overwrite the current one
        let cancelled = false;

        const fetchRevenue = async () => {
            setLoading(true);
            setError('');
            setData(null);
            try {
                // The tenant is derived from the auth token on the backend
                const response = await SecureAPI.getDashboardSummary(propertyId, {
                    month,
                    year,
                    timestamp: Date.now()
                });
                if (!cancelled) setData(response);
            } catch (err) {
                if (!cancelled) {
                    setError('Failed to load revenue data');
                    console.error(err);
                }
            } finally {
                if (!cancelled) setLoading(false);
            }
        };

        fetchRevenue();
        return () => {
            cancelled = true;
        };
    }, [propertyId, month, year]);

    if (loading) {
        return (
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
                <div className="animate-pulse space-y-4">
                    <div className="h-4 bg-gray-100 rounded w-1/4"></div>
                    <div className="h-8 bg-gray-100 rounded w-1/2"></div>
                    <div className="flex gap-4 pt-4">
                        <div className="h-12 bg-gray-100 rounded flex-1"></div>
                        <div className="h-12 bg-gray-100 rounded flex-1"></div>
                    </div>
                </div>
            </div>
        );
    }

    if (error) return <div className="p-4 text-red-500 bg-red-50 rounded-lg">{error}</div>;
    if (!data || data.property_id !== propertyId) return null;

    const displayTotal = formatMoney(data.total_revenue, data.currency);
    const periodLabel = data.month && data.year ? `${MONTH_NAMES[data.month - 1]} ${data.year}` : 'All time';

    return (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden hover:shadow-md transition-shadow duration-300">
            {showRaw && (
                <div className="p-3 bg-gray-50 text-xs font-mono border-b border-gray-100 overflow-auto max-h-32">
                    <strong className="block mb-1 text-gray-500 uppercase tracking-wider text-[10px]">Raw API Response</strong>
                    <pre className="text-gray-700">{JSON.stringify(data, null, 2)}</pre>
                </div>
            )}

            <div className="p-6">
                <div className="flex items-center justify-between mb-6">
                    <div>
                        <h2 className="text-sm font-medium text-gray-500 uppercase tracking-wide">Total Revenue &middot; {periodLabel}</h2>
                        <div className="flex items-baseline gap-2 mt-1">
                            <span className="text-3xl font-bold text-gray-900 tracking-tight">
                                {displayTotal}
                            </span>
                            {/* Fake trend indicator for premium feel */}
                            <span className="inline-flex items-baseline px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800 md:mt-2 lg:mt-0">
                                <svg className="-ml-1 mr-0.5 h-3 w-3 flex-shrink-0 self-center text-green-500" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
                                    <path fillRule="evenodd" d="M5.293 9.707a1 1 0 010-1.414l4-4a1 1 0 011.414 0l4 4a1 1 0 01-1.414 1.414L11 7.414V15a1 1 0 11-2 0V7.414L6.707 9.707a1 1 0 01-1.414 0z" clipRule="evenodd" />
                                </svg>
                                12%
                            </span>
                        </div>
                    </div>
                </div>

                <div className="grid grid-cols-2 gap-4 pt-4 border-t border-gray-100">
                    <div>
                        <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Property ID</p>
                        <p className="text-sm font-semibold text-gray-700 font-mono mt-1">{data.property_id}</p>
                    </div>
                    <div>
                        <p className="text-xs text-gray-500 font-medium uppercase tracking-wider">Reservations</p>
                        <p className="text-sm font-semibold text-gray-700 mt-1">{data.reservations_count} <span className="font-normal text-gray-400">bookings</span></p>
                    </div>
                </div>
            </div>
        </div>
    );
};
