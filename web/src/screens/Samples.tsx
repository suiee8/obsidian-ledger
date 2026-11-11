import { sampleFiles } from "../sampleCatalog";

export default function Samples() {
  return (
    <div className="page">
      <header className="page-header">
        <div>
          <p className="eyebrow">Fixtures · audit-friendly inputs</p>
          <h1>Sample files</h1>
          <p className="lede">
            These local fixtures exercise the import boundary: broker exports, raw executions, European number
            formats, duplicates, invalid rows, and instruction-like notes treated as data.
          </p>
        </div>
        <span className="badge">{sampleFiles.length} documented files</span>
      </header>

      <section className="glass table-wrap" aria-labelledby="samples-heading" tabIndex={0}>
        <h2 id="samples-heading">Fixture catalog</h2>
        <table>
          <thead>
            <tr>
              <th scope="col">File</th>
              <th scope="col">Source</th>
              <th scope="col">Shape</th>
              <th scope="col">Import note</th>
            </tr>
          </thead>
          <tbody>
            {sampleFiles.map((sample) => (
              <tr key={sample.file}>
                <td className="file">{sample.file}</td>
                <td>{sample.source}</td>
                <td>
                  <span className="badge">{sample.shape}</span>
                </td>
                <td className="muted-cell">{sample.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
