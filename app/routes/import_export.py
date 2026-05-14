from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
import json
from pathlib import Path
from werkzeug.datastructures import FileStorage
from io import BytesIO

from app.models.competitor import Competitor
from app.services.csv_export_service import export_competitor_products
from app.services.csv_import_service import import_csv
from app.services.notification_service import create_notification
from app.utils.helpers import safe_filename


bp = Blueprint("import_export", __name__)


@bp.route("/import", methods=["GET", "POST"])
def import_view():
    competitors = Competitor.query.order_by(Competitor.internal_code.asc()).all()

    if request.method == "POST":
        competitor_code = request.form.get("competitor_code", "").strip()
        uploaded = request.files.get("csv_file")
        
        if not competitor_code or not uploaded:
            flash("Alege codul intern al competitorului si fisierul CSV.", "warning")
            return redirect(url_for("import_export.import_view"))
        
        try:
            # Salveaza fisierul temporar
            target_path = Path(current_app.config["UPLOAD_FOLDER"]) / safe_filename(uploaded.filename)
            uploaded.save(target_path)
            
            # Extrage mappingul si categoria din formular
            mapping = {}
            for key in request.form.keys():
                if key.startswith("mapping[") and key.endswith("]"):
                    csv_col = key[8:-1]
                    field = request.form.get(key)
                    if field:
                        mapping[csv_col] = field

            default_categorie = request.form.get("default_categorie", "").strip() or None

            if not mapping:
                imported_count, _ = import_csv(
                    uploaded,
                    competitor_code,
                    current_app.config["UPLOAD_FOLDER"],
                    default_categorie=default_categorie,
                )
            else:
                file_content = target_path.read_text(encoding='utf-8')
                file_obj = FileStorage(
                    stream=BytesIO(file_content.encode('utf-8')),
                    filename=uploaded.filename,
                    name='csv_file'
                )
                imported_count, _ = import_csv(
                    file_obj,
                    competitor_code,
                    current_app.config["UPLOAD_FOLDER"],
                    mapping=mapping,
                    default_categorie=default_categorie,
                )
            
            create_notification(
                "Import finalizat",
                f"Au fost importate {imported_count} produse pentru {competitor_code}.",
                "success",
            )
            flash(f"Import reusit: {imported_count} produse.", "success")
            
            # Curata fisierul temporar
            try:
                target_path.unlink()
            except:
                pass
            
            return redirect(url_for("products.list_view"))
            
        except Exception as exc:
            current_app.logger.exception("Import failed")
            flash(f"Eroare la import: {str(exc)}", "danger")
            return redirect(url_for("import_export.import_view"))

    return render_template(
        "import_export/import.html",
        competitors=competitors,
    )


@bp.route("/export")
def export_view():
    competitors = Competitor.query.order_by(Competitor.internal_code.asc()).all()
    competitor_code = request.args.get("competitor_code", "").strip()
    if not competitor_code:
        return render_template("import_export/export.html", competitors=competitors)

    export_path, exported_count = export_competitor_products(
        competitor_code,
        current_app.config["EXPORT_FOLDER"],
    )
    create_notification(
        "Export generat",
        f"Au fost exportate {exported_count} produse pentru {competitor_code}.",
        "info",
    )
    return send_file(export_path, as_attachment=True)
