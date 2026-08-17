# Known Issues and Future Enhancements

This document tracks deferred issues, incomplete features, and planned enhancements for transparency and future development planning.

## Status: Production-Ready with Known Limitations

The platform is production-ready for its current scope (research, decision support, simulation). The items below are **intentional deferrals** or **future enhancements**, not blocking bugs.

---

## Accessibility (Deferred from Code Reviews)

### BaseTabs ARIA Implementation
**Status:** Deferred  
**Severity:** Medium  
**Context:** Task 16 review identified missing ARIA attributes in BaseTabs component

**Current State:**
- BaseTabs uses visual tab switching
- Basic keyboard navigation works
- Missing ARIA tablist/tab/tabpanel relationships

**Impact:**
- Screen reader users may not understand tab structure
- Reduced accessibility compliance

**Recommendation:**
- Add `role="tablist"` to tab container
- Add `role="tab"` and `aria-selected` to tab buttons
- Add `role="tabpanel"` to content areas
- Implement proper `aria-controls` and `id` linking

**Priority:** Should implement before public deployment

---

## Backend Integration (Intentional Mock State)

### API Endpoints Not Yet Implemented

**Status:** Mock data in frontend  
**Severity:** Expected  
**Context:** Phase 1-6 focused on UI/UX; backend integration deferred

**Not Yet Connected:**
- `/api/research/kline` - K-line data endpoint
- `/api/research/indicators` - Technical indicators
- `/api/research/evidence` - Evidence chain data
- `/api/backtest/run` - Real backtest execution
- Token usage real-time tracking API
- WebSocket real-time quote updates

**Current Behavior:**
- Frontend uses realistic mock data
- Simulates API responses with delays
- Data quality badges show "mock" status
- All UI workflows function correctly

**Impact:**
- Demo and development fully functional
- Cannot connect to real market data yet
- Backend API development can proceed independently

**Next Steps:**
1. Implement backend endpoints matching frontend contracts
2. Replace mock data with real API calls
3. Add error handling for network failures
4. Implement WebSocket server for real-time data

**Priority:** Required for production deployment

---

## Features Marked "功能开发中" (In Development)

### ResearchView - Backtest Draft Tab

**Status:** UI complete, backend pending  
**Components affected:** `BacktestDraft.vue`, `BacktestPreview.vue`

**Current State:**
- Form fully implemented with validation
- Configuration options available
- Buttons disabled with "功能开发中" hint
- Preview component shows placeholder

**Missing:**
- Backend backtest execution
- Real-time progress updates
- Results visualization
- Historical backtest comparison

**Timeline:** Backend integration phase

### DecisionView - Automatic Push Eligibility

**Status:** Workflow implemented, automation pending  
**Component:** `DecisionView.vue`

**Current State:**
- Eligibility checks defined and displayed
- Manual analysis workflow complete
- Safety boundaries enforced
- All checks visible to user

**Missing:**
- Automatic notification delivery
- Integration with external notification services
- Push approval workflow
- Delivery status tracking

**Rationale:** Safety-critical feature requiring thorough testing

**Timeline:** Post-deployment after manual validation period

### AI Runtime Provider Integration

**Status:** UI complete, some providers pending  
**Context:** Task 19 - Token usage tracking ready

**Current State:**
- OpenAI-compatible provider support
- Token usage tracking and cost calculation
- Demo data generation
- Provider configuration UI

**Missing:**
- Real-time token streaming from actual LLM calls
- Provider health monitoring integration
- Multi-provider cost comparison
- Budget alerts and limits

**Timeline:** Incremental rollout per provider

---

## Mobile-Specific Considerations

### Wide Workspace Pages on Mobile

**Status:** Intentional design decision  
**Pages affected:** Screener, Strategy Workbench, Alpha Factors, Validation

**Design Decision:**
- These pages marked as "移动端横向数据区" (mobile horizontal data area)
- Tables and complex data grids require horizontal scroll
- Optimized for landscape mode or larger viewports
- Touch gestures work correctly

**Rationale:**
- Complex data tables cannot meaningfully collapse to single column
- Professional traders typically use tablets/desktop
- Mobile support provided for monitoring, not primary workflow

**User Guidance:**
- Documentation notes these pages best viewed on tablet/desktop
- Mobile users can rotate to landscape
- Core workflows (Research, Decision) fully mobile-optimized

### Touch Target Sizes

**Status:** Generally compliant, some exceptions  
**Standard:** WCAG 2.1 Level AAA (44x44px minimum)

**Current State:**
- Primary buttons meet 44px minimum
- Icon buttons use 40px (acceptable for Level AA)
- Compact tables use 36px rows with adequate spacing
- All interactive elements have visible touch areas

**Exceptions:**
- Data table action icons: 32-36px (still tappable with spacing)
- Tag badges: Non-interactive, no touch target requirement
- Inline text links: Follow line height, no minimum

**Improvement Plan:**
- Add touch-target-extension utility class
- Increase compact icon button base size to 40px
- Add visual feedback for all touch interactions

---

## Performance Optimizations (Future)

### Bundle Size Optimization

**Current State:**
- Main bundle: ~180KB gzipped (within 200KB target)
- Code splitting implemented for routes
- Lazy loading for heavy components
- Tree shaking enabled

**Future Optimizations:**
- Lazy load lucide-vue-next icons individually
- Split vendor bundle further
- Implement virtual scrolling for long lists
- Add service worker for offline caching

**Priority:** Nice to have, not blocking

### Chart Rendering Performance

**Status:** Acceptable for current data volumes  
**Context:** K-line charts, backtest results

**Current Performance:**
- Renders 500 data points smoothly
- Interactive pan/zoom functional
- Updates without flicker

**Future Improvements:**
- Canvas rendering for 1000+ points
- WebGL for real-time tick data
- Incremental data loading
- Data decimation for zoomed-out views

**Priority:** Required for tick-level data

---

## Security Hardening (Pre-Production Checklist)

### Items to Address Before Public Deployment

**API Security:**
- [ ] Rate limiting on all endpoints
- [ ] API key rotation mechanism
- [ ] Request signing for sensitive operations
- [ ] CSRF protection for state-changing requests

**Authentication:**
- [ ] OAuth2/OIDC integration (currently mock)
- [ ] Session timeout enforcement
- [ ] Concurrent session limits
- [ ] Audit logging for auth events

**Data Protection:**
- [ ] Input validation on all API inputs
- [ ] SQL injection prevention (using SQLAlchemy safely)
- [ ] XSS prevention (Vue automatically escapes)
- [ ] Sensitive data encryption at rest

**Infrastructure:**
- [ ] HTTPS enforcement in production
- [ ] Security headers (CSP, HSTS, etc.)
- [ ] Dependency vulnerability scanning (npm audit)
- [ ] Regular security updates

**Status:** Development environment secure, production hardening needed

---

## Testing Gaps

### Current Test Coverage

**Backend:**
- Unit tests: ~70% coverage
- Integration tests: Core workflows covered
- API tests: Major endpoints tested

**Frontend:**
- Component tests: Base components covered
- Integration tests: ResearchView (35 tests)
- E2E tests: Critical paths covered
- Mobile tests: 20 tests added in Task 20

**Gaps:**
- DecisionView integration tests (complex workflow)
- MoreView sub-pages (lower priority)
- Error boundary testing
- WebSocket reconnection scenarios
- Accessibility automated testing

**Priority:** Add DecisionView tests before v1.0

---

## Documentation Needs

### User Documentation

**Missing:**
- User guide with screenshots
- Workflow tutorials
- Video demos
- FAQ section
- Troubleshooting guide

**Priority:** Required for user onboarding

### API Documentation

**Current State:**
- Inline docstrings present
- FastAPI auto-generated docs available at `/docs`
- Type hints complete

**Missing:**
- API versioning strategy
- Rate limits documentation
- Webhook documentation
- SDK examples

**Priority:** Required for integration partners

### Deployment Documentation

**Current State:**
- Docker Compose setup documented
- Environment variables listed

**Missing:**
- Production deployment guide
- Kubernetes manifests
- Monitoring setup guide
- Backup and recovery procedures
- Scaling guidelines

**Priority:** Required for production operations

---

## Future Enhancements

### Phase 7+ Roadmap Items

**Real-Time Features:**
- WebSocket price streaming (infrastructure ready)
- Live order book updates
- Real-time P&L tracking
- Push notifications for alerts

**Advanced Analytics:**
- Machine learning model management UI
- Custom indicator builder
- Strategy parameter optimization UI
- Portfolio rebalancing automation

**Collaboration:**
- Shared research notes
- Strategy sharing marketplace
- Team workspaces
- Audit trail for team actions

**Integrations:**
- Broker API connections (CTP, XTP)
- Third-party data providers
- Notification services (email, SMS, WeChat)
- Calendar integrations for earnings/events

---

## How to Use This Document

**For Developers:**
- Check this list before claiming issues are bugs
- Reference for understanding design decisions
- Prioritize fixes based on severity and timeline

**For Product Managers:**
- Use for feature roadmap planning
- Communicate limitations to stakeholders
- Track completion of deferred items

**For QA:**
- Known issues don't require bug reports
- Focus testing on unlisted scenarios
- Verify documented workarounds

**For Users:**
- Understand platform capabilities and limits
- Workarounds for known issues
- Preview of upcoming features

---

## Contributing

If you encounter an issue not listed here:
1. Check if it's truly a bug or expected behavior
2. Search existing GitHub issues
3. Create a new issue with detailed reproduction steps
4. Reference this document if related to a known limitation

---

**Last Updated:** 2026-08-17  
**Platform Version:** 0.9.0  
**Phase Status:** Phase 6 Complete - Production Ready
