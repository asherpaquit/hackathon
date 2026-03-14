# FreightScan AI — Project Roadmap & Progress Plan

**Status**: Alpha (Incomplete, Unfinished, Baseline Accuracy)
**Target**: Beta (Polished, Production-ready, High Accuracy)

---

## 📊 Current State (Demo Phase)

### ✅ Completed
- PDF extraction (pdfplumber + regex)
- LLM-based rate table parsing (Ollama qwen2.5:3b)
- Basic port normalization (hardcoded mapping + regex)
- Origin name cleaning (multi-regex fallback chain)
- Commodity-coded rate handling (regex capture groups)
- Excel export (openpyxl → ATL template)
- Low-memory optimization (8GB RAM, 3B model)
- Column filtering (_ignore sentinel)

### ❌ Known Gaps / Issues
1. **Accuracy**: Baseline only — not tested across diverse PDF formats
2. **Port variants**: Only ~50 ports mapped; missing many regional variants
3. **Currency handling**: Hardcoded USD; no multi-currency support
4. **Rate validation**: No range checks or outlier detection
5. **UI/UX**: Basic React upload; no progress tracking or error feedback
6. **Testing**: No unit tests, integration tests, or accuracy benchmarks
7. **Performance**: Single-threaded processing; no parallelization
8. **Robustness**: Crashes on unexpected table structures
9. **Logging**: Minimal debugging info for failed extractions
10. **Documentation**: No API docs, no user guide

---

## 🎯 Phase 1: Accuracy Foundation (Weeks 1-2)

### Goal
Validate and improve extraction accuracy across 10+ diverse freight PDFs (different formats, languages, layouts).

### Tasks

#### 1.1 Accuracy Benchmarking
- [ ] Create test dataset (10-15 real PDFs from different shippers/routes)
- [ ] Manually extract ground truth Excel for each PDF
- [ ] Build accuracy metrics script:
  - `field_accuracy`: % of correct extracted values per field
  - `rate_accuracy`: Mean absolute error (MAE) on rates
  - `origin_accuracy`: % of correctly normalized origins
  - `destination_accuracy`: % of correctly mapped ports
- [ ] Establish baseline accuracy scores for demo

#### 1.2 Port Variant Expansion
- [ ] Analyze test dataset for unique port names
- [ ] Extract 100+ new port variants (China ports, SE Asia, Middle East)
- [ ] Add regex patterns for:
  - Province qualifiers (`DALIAN, LIAONING` → `DALIAN`)
  - Terminal/wharf suffixes (`YANTIAN TERMINAL` → `YANTIAN`)
  - Country codes (`SHANGHAI CN` → `SHANGHAI`)
- [ ] Implement fuzzy matching fallback (90%+ similarity)
- [ ] Update `PORT_MAP` to 300+ entries

**Expected impact**: +15-20% destination accuracy

#### 1.3 Rate Extraction Robustness
- [ ] Add rate validation rules:
  - Reject rates < $10 or > $50,000 (outliers)
  - Flag rates that don't match currency format
  - Warn if rate cell contains multiple numbers
- [ ] Handle edge cases:
  - Ranges: `2500-2800` → use midpoint or flag
  - Surcharges: `2500 + 150 BAF` → extract base rate separately
  - Non-ASCII characters: ¥, €, £, ₹ support
- [ ] Add fallback to image OCR if table parsing fails

**Expected impact**: +5-10% rate accuracy

#### 1.4 Origin Normalization Improvements
- [ ] Expand cleaning regex for:
  - Airport codes: `(PVG)`, `(SHA)` stripping
  - Shipping terms: `(CY/CY)`, `(FCL/FCL)`, `(LCL/LCL)`
  - Chinese province names: `上海`, `广东`, etc. → pinyin
- [ ] Add language detection (Chinese, Korean, Vietnamese)
- [ ] Build multilingual port database

**Expected impact**: +10% origin accuracy

#### 1.5 Column & Field Detection
- [ ] Auto-detect column headers (no hardcoding `_RATE_COL`)
- [ ] Handle variable column orders
- [ ] Recognize hidden/merged cells
- [ ] Support alternative field names:
  - Rate: `Price`, `Charge`, `Fee`, `Tariff`
  - Origin: `Shipper Port`, `Load Port`, `Pickup`
  - Destination: `Consignee Port`, `Discharge Port`, `Delivery`

**Expected impact**: Support any freight contract template

---

## 🚀 Phase 2: Performance & Scalability (Weeks 3-4)

### Goal
Process 100+ PDFs/day with <5 min per 200-page contract.

### Tasks

#### 2.1 Parallel Processing
- [ ] Implement ThreadPoolExecutor:
  - Parallel PDF extraction (multi-table parsing)
  - Concurrent Ollama requests (queue-based batching)
- [ ] Add request throttling (avoid OOM)
- [ ] Benchmark: Measure speedup vs. single-threaded

**Expected impact**: 2-3x faster processing

#### 2.2 Model Optimization
- [ ] Test alternative models:
  - `mistral:7b` (faster, lower quality?)
  - `neural-chat:7b` (domain-specific?)
  - `qwen2.5:7b` (higher accuracy at cost of speed?)
- [ ] Implement model selection UI (user chooses speed vs. accuracy)
- [ ] Add quantization for 4GB RAM fallback

**Expected impact**: 30-50% faster without losing accuracy

#### 2.3 Caching & Deduplication
- [ ] Cache normalized port mappings (Redis or SQLite)
- [ ] Detect duplicate rate entries (same origin/destination/rate)
- [ ] Implement incremental processing (skip unchanged pages)

**Expected impact**: 50% faster on re-runs

#### 2.4 Database Backend
- [ ] Replace hardcoded `PORT_MAP` with PostgreSQL
- [ ] Store historical extraction results
- [ ] Track accuracy metrics over time
- [ ] Enable user feedback loop (mark errors, re-train)

---

## 🎨 Phase 3: UX & User Experience (Weeks 5-6)

### Goal
Make the app intuitive, transparent, and production-ready.

### Tasks

#### 3.1 Enhanced Upload & Progress Tracking
- [ ] Real-time progress bar:
  - "Parsing PDF..." → 10%
  - "Extracting rates..." → 40%
  - "Normalizing data..." → 70%
  - "Exporting Excel..." → 95%
- [ ] Show extraction details:
  - Pages processed: 45/186
  - Tables found: 12
  - Rates extracted: 342
  - Unknown ports: 3 (show them)
- [ ] Cancel button for long-running jobs

#### 3.2 Error Handling & User Feedback
- [ ] Graceful error messages:
  - ❌ Instead of: `IndexError: list index out of range`
  - ✅ Show: `Could not find rate table on page 45. Please check the PDF format.`
- [ ] Flag suspicious data:
  - ⚠️ "Rate $50,000 seems high — double-check"
  - ⚠️ "Port 'UNKNOWN_CITY' not recognized — manually verify"
- [ ] Email extraction report with:
  - Summary stats
  - Warnings/errors
  - Download link

#### 3.3 Batch Processing UI
- [ ] Upload multiple PDFs at once
- [ ] Queue management (show job status for 100 files)
- [ ] Bulk download results as ZIP
- [ ] Scheduled extractions (run nightly)

#### 3.4 Comparison & Review Mode
- [ ] Side-by-side comparison:
  - Original PDF ↔ Extracted Excel
  - Show which cells were auto-filled
- [ ] One-click corrections:
  - Click on value → edit → confirm
  - Auto-learns for future extractions
- [ ] Export correction log (for re-training LLM)

---

## 🧪 Phase 4: Testing & Validation (Weeks 7-8)

### Goal
Ensure 95%+ accuracy and zero data loss.

### Tasks

#### 4.1 Unit Tests
- [ ] Test each component:
  - `test_pdf_extraction.py` (pdfplumber parsing)
  - `test_rate_extraction.py` (regex + LLM)
  - `test_normalization.py` (port mapping, origin cleaning)
  - `test_excel_export.py` (formatting, columns)
- [ ] Target: 80%+ code coverage

#### 4.2 Integration Tests
- [ ] End-to-end pipeline:
  - PDF upload → API → Excel download
  - Verify all fields populated correctly
- [ ] Edge cases:
  - Empty tables
  - Single-row tables
  - Tables with merged cells
  - Multiple languages
  - Corrupted PDFs

#### 4.3 Accuracy Benchmarking (Cross-Format)
- [ ] Test on 5 freight PDF formats:
  - LAX (Mediterranean containers)
  - ATL (Atlantic routes)
  - Asia-Pacific regional
  - Reefer (temperature-controlled)
  - LCL (less-than-container)
- [ ] Measure accuracy per format
- [ ] Identify format-specific issues

#### 4.4 Load Testing
- [ ] Stress test with:
  - 50 concurrent uploads
  - 500-page PDFs
  - High-frequency API calls
- [ ] Monitor: Memory, CPU, response time
- [ ] Set SLA: <10s response time for <500MB uploads

---

## 📈 Phase 5: Advanced Features (Weeks 9-10)

### Goal
Add differentiating features for competitive advantage.

### Tasks

#### 5.1 Contract Comparison
- [ ] Upload two freight contracts
- [ ] Highlight differences (rates, surcharges, effective dates)
- [ ] Flag price increases/decreases
- [ ] Export comparison report

#### 5.2 Rate Trend Analytics
- [ ] Track historical rates per route
- [ ] Show price trends (📈 up, 📉 down, ➡️ flat)
- [ ] Predict future rates (linear regression)
- [ ] Alert on unusual rate spikes

#### 5.3 Multi-Format Export
- [ ] Export to:
  - CSV (for data integration)
  - JSON (for APIs)
  - PDF (formatted report)
  - Google Sheets (auto-sync)
  - SAP/Oracle integration

#### 5.4 Supplier Network
- [ ] Build supplier database:
  - Extract shipper/carrier names
  - Link to historical rates
  - Show all active contracts
- [ ] Compliance dashboard:
  - Are all suppliers terms met?
  - Contract expiration alerts

#### 5.5 API for Third Parties
- [ ] RESTful API:
  - `POST /extract` (upload PDF)
  - `GET /status/{job_id}` (check progress)
  - `GET /results/{job_id}` (download Excel)
- [ ] Rate limiting: 100 req/day free tier
- [ ] Webhook for async jobs

---

## 🔒 Phase 6: Compliance & Deployment (Weeks 11-12)

### Goal
Production-ready with security, compliance, and monitoring.

### Tasks

#### 6.1 Security Hardening
- [ ] Input validation:
  - Max file size: 100MB
  - Allowed MIME types: only PDF
  - Scan for malware (ClamAV)
- [ ] Rate limiting (prevent DoS)
- [ ] CORS configuration
- [ ] Encrypt uploaded PDFs at rest
- [ ] Auto-delete PDFs after 24h

#### 6.2 Compliance & Documentation
- [ ] Privacy policy (GDPR compliant)
- [ ] User guide + video tutorials
- [ ] API documentation (OpenAPI/Swagger)
- [ ] SLA documentation
- [ ] Audit logs (who extracted what, when)

#### 6.3 Monitoring & Observability
- [ ] Logging:
  - Extraction success/failure rates
  - LLM response times
  - Error traces
- [ ] Metrics dashboard:
  - Daily active users
  - Avg extraction time
  - Top errors
- [ ] Alerting:
  - Failed extractions > 5%
  - API response time > 15s
  - Ollama service down

#### 6.4 Deployment
- [ ] Docker containerization
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Staging environment
- [ ] Blue-green deployment
- [ ] Rollback strategy

---

## 📊 Success Metrics

### Accuracy (Target: 95%+)
- [ ] Field accuracy: 95% of values match ground truth
- [ ] Rate accuracy: MAE < 2% of average rate
- [ ] Port accuracy: 98% of destinations correctly mapped
- [ ] Origin accuracy: 90% of origins correctly normalized

### Performance (Target: <5 min per 200-page PDF)
- [ ] Avg extraction time: 3 min
- [ ] P95 latency: <6 min
- [ ] Throughput: 100 PDFs/day on single server

### Availability (Target: 99.5%)
- [ ] Uptime: 99.5% SLA
- [ ] Mean time to recovery (MTTR): <30 min
- [ ] Failed extractions: <1% of submissions

### User Experience
- [ ] Error handling: 0 unhandled exceptions visible to users
- [ ] UI responsiveness: <2s page load time
- [ ] User satisfaction: >4.5/5 stars

---

## 🗓️ Timeline

| Phase | Duration | Key Deliverable |
|-------|----------|-----------------|
| **Phase 1: Accuracy** | Weeks 1-2 | Benchmark report, port DB with 300+ entries |
| **Phase 2: Performance** | Weeks 3-4 | 2-3x speedup, model selection UI |
| **Phase 3: UX** | Weeks 5-6 | Progress tracking, batch upload, error handling |
| **Phase 4: Testing** | Weeks 7-8 | 80%+ test coverage, accuracy reports per format |
| **Phase 5: Advanced** | Weeks 9-10 | Rate analytics, contract comparison, API |
| **Phase 6: Production** | Weeks 11-12 | Docker, monitoring, compliance docs |

---

## 🚨 Critical Path (MVP → Production)

**Must have for Beta release:**
1. ✅ Accuracy benchmarking (95%+ baseline)
2. ✅ Port variant expansion (300+ entries)
3. ✅ Error handling (no crashes)
4. ✅ Progress UI (transparency)
5. ✅ Unit tests (80%+ coverage)
6. ✅ Docker deployment
7. ✅ Monitoring/logging

**Nice to have:**
- Rate trend analytics
- Contract comparison
- Supplier network
- Third-party API

---

## 🤝 Team Contributions

### Backend (Python)
- Expand port/currency databases
- Implement LLM prompt optimization
- Build test suite
- Deploy to production

### Frontend (React)
- Build progress tracking UI
- Implement error messaging
- Add batch upload
- Create comparison views

### DevOps
- Docker containerization
- CI/CD pipeline
- Monitoring setup
- Database migrations

### QA/Testing
- Accuracy benchmarking
- Cross-format testing
- Load testing
- User feedback collection

---

## 📝 Notes

- **Current accuracy**: Baseline (not yet measured across diverse formats)
- **Current performance**: ~5 min per 200-page PDF (single-threaded)
- **Current reliability**: Works for standard contract layouts; crashes on edge cases
- **Demo goal**: Show potential, gather user feedback, identify must-fix bugs

---

## 🎯 Conclusion

FreightScan AI is **functionally complete for MVP** but **needs polish for production**. The roadmap prioritizes:

1. **Accuracy first** — ensure extraction is reliable across all freight formats
2. **Performance second** — 2-3x speedup through parallelization
3. **UX third** — transparency and error handling for enterprise adoption
4. **Scaling last** — when we have users, add advanced features

**Expected outcome**: Production-ready, 95%+ accurate, 3-min processing time, <2% error rate by Week 12.

